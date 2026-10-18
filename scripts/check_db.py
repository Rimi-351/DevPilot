import os, sqlite3

def main():
    # Resolve DB path (default SQLite file location)
    db_path = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./devpilot.db')
    # Strip SQLAlchemy prefix if present
    if db_path.startswith('sqlite+'):  # e.g., "sqlite+aiosqlite:///./devpilot.db"
        db_path = db_path.split('///')[-1]
    db_path = os.path.abspath(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # recent processing jobs
    cur.execute("SELECT id, status, error_message FROM processing_job ORDER BY created_at DESC LIMIT 5")
    jobs = cur.fetchall()
    print('Recent ProcessingJobs:')
    for j in jobs:
        print(dict(j))
    # chunk counts per project
    cur.execute("SELECT project_id, COUNT(*) as cnt FROM document_chunk GROUP BY project_id")
    chunks = cur.fetchall()
    print('DocumentChunk counts per project:')
    for c in chunks:
        print(dict(c))
    conn.close()

if __name__ == '__main__':
    main()
