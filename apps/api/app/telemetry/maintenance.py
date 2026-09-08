from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from app.db.session import engine

def maintain_partitions(days_back=7, days_forward=2):
    """
    Ensures that partitions exist for the specified window.
    Drops partitions older than days_back.
    """
    now = datetime.now(timezone.utc)
    
    with engine.begin() as conn:
        if engine.dialect.name != 'postgresql':
            return
            
        for i in range(-days_back, days_forward + 1):
            target_date = now + timedelta(days=i)
            partition_name = f"telemetry_p{target_date.strftime('%Y_%m_%d')}"
            
            start_bound = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_bound = start_bound + timedelta(days=1)
            
            start_str = start_bound.strftime('%Y-%m-%d %H:%M:%S+00')
            end_str = end_bound.strftime('%Y-%m-%d %H:%M:%S+00')
            
            stmt = f"""
            CREATE TABLE IF NOT EXISTS {partition_name} 
            PARTITION OF telemetry 
            FOR VALUES FROM ('{start_str}') TO ('{end_str}');
            """
            conn.execute(text(stmt))
            
        query = text("""
            SELECT child.relname 
            FROM pg_inherits 
            JOIN pg_class parent ON pg_inherits.inhparent = parent.oid 
            JOIN pg_class child ON pg_inherits.inhrelid = child.oid 
            WHERE parent.relname = 'telemetry';
        """)
        partitions = conn.execute(query).fetchall()
        
        valid_suffixes = [
            f"p{(now + timedelta(days=i)).strftime('%Y_%m_%d')}"
            for i in range(-days_back, days_forward + 1)
        ]
        
        for (part_name,) in partitions:
            if not any(part_name.endswith(suffix) for suffix in valid_suffixes):
                conn.execute(text(f"DROP TABLE IF EXISTS {part_name};"))

if __name__ == "__main__":
    maintain_partitions()
