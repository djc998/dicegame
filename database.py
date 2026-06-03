import aiosqlite
import logging
import os
from datetime import datetime

DB_PATH = os.path.join("data", "dice_game.db")

async def init_db():
    """Initializes the database schema."""
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                has_account_license BOOLEAN DEFAULT 0
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                group_id INTEGER PRIMARY KEY,
                group_title TEXT,
                install_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                trial_start TIMESTAMP,
                is_premium BOOLEAN DEFAULT 0,
                default_game_time INTEGER DEFAULT 30,
                cooldown_minutes INTEGER DEFAULT 5
            )
        ''')
        
        try:
            await db.execute('ALTER TABLE groups ADD COLUMN group_title TEXT')
        except aiosqlite.OperationalError:
            pass # Column already exists
            
        try:
            await db.execute('ALTER TABLE groups ADD COLUMN owner_id INTEGER')
        except aiosqlite.OperationalError:
            pass # Column already exists
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS games (
                game_id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                announcement_msg_id INTEGER,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (group_id) REFERENCES groups (group_id)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS player_cooldowns (
                player_id INTEGER,
                group_id INTEGER,
                last_roll_time TIMESTAMP,
                PRIMARY KEY (player_id, group_id)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS submissions (
                submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER,
                player_id INTEGER,
                player_name TEXT,
                message_id INTEGER,
                score_sum INTEGER DEFAULT 0,
                vote_count INTEGER DEFAULT 0,
                FOREIGN KEY (game_id) REFERENCES games (game_id)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS votes (
                submission_id INTEGER,
                voter_id INTEGER,
                score INTEGER,
                PRIMARY KEY (submission_id, voter_id),
                FOREIGN KEY (submission_id) REFERENCES submissions (submission_id)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS dice_faces (
                face_id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER,
                face_type TEXT,
                value TEXT,
                UNIQUE(group_id, face_type, value)
            )
        ''')
        await db.commit()

async def get_or_create_group(group_id: int, group_title: str = None, owner_id: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM groups WHERE group_id = ?', (group_id,)) as cursor:
            group = await cursor.fetchone()
            if not group:
                final_title = group_title or "Unknown Group"
                await db.execute('INSERT INTO groups (group_id, group_title, owner_id) VALUES (?, ?, ?)', (group_id, final_title, owner_id))
                await db.commit()
                async with db.execute('SELECT * FROM groups WHERE group_id = ?', (group_id,)) as new_cursor:
                    group = await new_cursor.fetchone()
            else:
                update_needed = False
                if group_title and group['group_title'] != group_title:
                    await db.execute('UPDATE groups SET group_title = ? WHERE group_id = ?', (group_title, group_id))
                    update_needed = True
                    
                if owner_id is not None and group['owner_id'] is None:
                    await db.execute('UPDATE groups SET owner_id = ? WHERE group_id = ?', (owner_id, group_id))
                    update_needed = True
                    
                if update_needed:
                    await db.commit()
                    async with db.execute('SELECT * FROM groups WHERE group_id = ?', (group_id,)) as new_cursor:
                        group = await new_cursor.fetchone()
            
            group_dict = dict(group)
            
            # Auto-grant premium if owner has account license
            if group_dict.get('owner_id'):
                async with db.execute('SELECT has_account_license FROM users WHERE user_id = ?', (group_dict['owner_id'],)) as acct_cursor:
                    row = await acct_cursor.fetchone()
                    if row and row[0]:
                        group_dict['is_premium'] = 1
            
            return group_dict

async def create_game(group_id: int, end_time: datetime, announcement_msg_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('''
            INSERT INTO games (group_id, end_time, announcement_msg_id, is_active)
            VALUES (?, ?, ?, 1)
        ''', (group_id, end_time, announcement_msg_id))
        await db.commit()
        return cursor.lastrowid

async def get_active_game(group_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT * FROM games 
            WHERE group_id = ? AND is_active = 1 
            ORDER BY start_time DESC LIMIT 1
        ''', (group_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def end_game(game_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE games SET is_active = 0 WHERE game_id = ?', (game_id,))
        await db.commit()

async def get_player_cooldown(player_id: int, group_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT last_roll_time FROM player_cooldowns 
            WHERE player_id = ? AND group_id = ?
        ''', (player_id, group_id)) as cursor:
            row = await cursor.fetchone()
            return dict(row)['last_roll_time'] if row else None

async def update_player_cooldown(player_id: int, group_id: int, roll_time: datetime):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO player_cooldowns (player_id, group_id, last_roll_time)
            VALUES (?, ?, ?)
            ON CONFLICT(player_id, group_id) DO UPDATE SET last_roll_time = excluded.last_roll_time
        ''', (player_id, group_id, roll_time))
        await db.commit()

async def create_submission(game_id: int, player_id: int, player_name: str, message_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('''
            INSERT INTO submissions (game_id, player_id, player_name, message_id)
            VALUES (?, ?, ?, ?)
        ''', (game_id, player_id, player_name, message_id))
        await db.commit()
        return cursor.lastrowid

async def get_submission_by_msg(message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM submissions WHERE message_id = ?', (message_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def add_vote(submission_id: int, voter_id: int, score: int) -> bool:
    """Returns True if vote was successful, False if already voted."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute('''
                INSERT INTO votes (submission_id, voter_id, score)
                VALUES (?, ?, ?)
            ''', (submission_id, voter_id, score))
            
            # Update the aggregate score
            await db.execute('''
                UPDATE submissions 
                SET score_sum = score_sum + ?, vote_count = vote_count + 1
                WHERE submission_id = ?
            ''', (score, submission_id))
            
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

async def get_top_submission(game_id: int):
    """Returns the winning submission based on average score."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT *, CAST(score_sum AS FLOAT) / vote_count AS avg_score 
            FROM submissions 
            WHERE game_id = ? AND vote_count > 0
            ORDER BY avg_score DESC
            LIMIT 1
        ''', (game_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_dice_faces(group_id: int, face_type: str) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Ensure existing groups get seeded with default dice faces if they have none
        async with db.execute('SELECT COUNT(*) FROM dice_faces WHERE group_id = ?', (group_id,)) as count_cursor:
            count = await count_cursor.fetchone()
            if count[0] == 0:
                actions = ["Take a picture", "Make a video", "Go Live", "Audio of", "Wildest Fantasy"]
                subjects = ["Head", "Foot", "Chest", "Leg", "Hand"]
                for action in actions:
                    await db.execute('INSERT INTO dice_faces (group_id, face_type, value) VALUES (?, ?, ?)', (group_id, 'action', action))
                for subject in subjects:
                    await db.execute('INSERT INTO dice_faces (group_id, face_type, value) VALUES (?, ?, ?)', (group_id, 'subject', subject))
                await db.commit()

        async with db.execute('SELECT value FROM dice_faces WHERE group_id = ? AND face_type = ?', (group_id, face_type,)) as cursor:
            rows = await cursor.fetchall()
            return [row['value'] for row in rows]

async def add_dice_face(group_id: int, face_type: str, value: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute('INSERT INTO dice_faces (group_id, face_type, value) VALUES (?, ?, ?)', (group_id, face_type, value))
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

async def remove_dice_face(group_id: int, face_type: str, value: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('DELETE FROM dice_faces WHERE group_id = ? AND face_type = ? AND value = ?', (group_id, face_type, value))
        await db.commit()
        return cursor.rowcount > 0

async def get_groups_by_owner(owner_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT group_id, group_title FROM groups WHERE owner_id = ?', (owner_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def set_group_premium(group_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE groups SET is_premium = 1 WHERE group_id = ?', (group_id,))
        await db.commit()

async def set_user_account_license(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO users (user_id, has_account_license) VALUES (?, 1)
            ON CONFLICT(user_id) DO UPDATE SET has_account_license = 1
        ''', (user_id,))
        await db.commit()

async def get_global_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM groups') as cursor:
            total_groups = (await cursor.fetchone())[0]
            
        async with db.execute('SELECT COUNT(*) FROM games') as cursor:
            total_games = (await cursor.fetchone())[0]
            
        avg_games = round(total_games / total_groups, 2) if total_groups > 0 else 0
        
        return {
            "total_groups": total_groups,
            "total_games": total_games,
            "avg_games_per_group": avg_games
        }

async def get_all_groups_list() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT g.group_id, g.group_title, g.owner_id, g.is_premium, u.has_account_license 
            FROM groups g
            LEFT JOIN users u ON g.owner_id = u.user_id
        ''') as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_owner_stats(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM groups WHERE owner_id = ?', (user_id,)) as cursor:
            total_owned_groups = (await cursor.fetchone())[0]
            
        async with db.execute('''
            SELECT COUNT(*) FROM games 
            INNER JOIN groups ON games.group_id = groups.group_id 
            WHERE groups.owner_id = ?
        ''', (user_id,)) as cursor:
            total_owned_games = (await cursor.fetchone())[0]
            
        async with db.execute('SELECT has_account_license FROM users WHERE user_id = ?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            has_license = bool(row and row[0])
            
        return {
            "total_owned_groups": total_owned_groups,
            "total_owned_games": total_owned_games,
            "has_account_license": has_license
        }
