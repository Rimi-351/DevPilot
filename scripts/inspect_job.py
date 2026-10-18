import os, sqlite3

def main():
    db_path = os.path.abspath('devpilot.db')
    if not os.path.exists(db_path):
        print('Database not found:', db_path)
        return
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # latest job
    cur.execute('SELECT id, project_id, status, error_message FROM processing_jobs ORDER BY id DESC LIMIT 1')
    job = cur.fetchone()
    print('Latest job:', job)
    if job:
        job_id, project_id, status, error_message = job
        print('Status:', status)
        if error_message:
            print('Error message:', error_message)
        # count chunks for project
        cur.execute('SELECT COUNT(*) FROM document_chunk WHERE project_id = ?', (project_id,))
        cnt = cur.fetchone()[0]
        print('DocumentChunk count for project:', cnt)
    conn.close()

if __name__ == '__main__':
    main()
