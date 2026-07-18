import os
from celery import Celery
from celery.schedules import crontab

redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "automation_tasks",
    broker=redis_url,
    backend=redis_url,
    include=['tasks']
)

celery_app.conf.update(
    timezone='Asia/Ho_Chi_Minh',
    enable_utc=True,
    # Cấu hình lịch chạy Beat (mỗi 15 phút)
    beat_schedule={
        'analyze-ads-every-15-mins': {
            'task': 'tasks.analyze_and_adjust_ads',
            'schedule': crontab(minute='*/15'),
        },
        'monitor-system-every-minute': {
            'task': 'tasks.monitor_system',
            'schedule': crontab(minute='*'),
        },
        'auto-post-facebook-daily': {
            'task': 'tasks.auto_post_facebook',
            'schedule': crontab(hour=9, minute=0),
        },
        'auto-post-blog-every-30-mins': {
            'task': 'tasks.auto_post_blog',
            'schedule': crontab(minute='*/30'),
        },
    }
)
