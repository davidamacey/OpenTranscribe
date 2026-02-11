# Cache Invalidation Guide

## Overview

OpenTranscribe uses a two-tier caching system:
1. **Backend Redis Cache** - Server-side API response caching
2. **Frontend In-Memory Cache** - Client-side response caching (60s TTL for status)

## Cache Invalidation Flow

```
Database Change
    ↓
Backend Service (normal code path)
    ↓
Redis Cache Invalidation
    ↓
WebSocket Notification → cache_invalidate
    ↓
Frontend Receives Notification
    ↓
Frontend Clears In-Memory Cache
    ↓
Next API Call Gets Fresh Data
```

## When Cache Doesn't Invalidate

**Problem:** Direct database changes (SQL, Python scripts) bypass the service layer.

**Symptoms:**
- UI shows old data after database update
- Browser refresh doesn't help (frontend cache still has stale data)
- API returns correct data, but frontend shows cached version

**Solution:** Manually trigger cache invalidation after direct DB changes.

---

## Manual Cache Invalidation Methods

### Method 1: Backend Python (After DB Scripts)

```python
# Add this after any direct database modification
from app.services.redis_cache_service import redis_cache

# Invalidate specific scope
redis_cache.invalidate_user_files(user_id)  # Files + status
redis_cache.invalidate_tags(user_id)         # Tags
redis_cache.invalidate_speakers(user_id)     # Speakers

# Or nuclear option
redis_cache.invalidate_all_for_user(user_id)

# Then send WebSocket notification to frontend
import asyncio
from app.api.websockets import send_notification

async def notify():
    await send_notification(
        user_id=user_id,
        notification_type='cache_invalidate',
        data={'scope': 'all'}
    )

asyncio.run(notify())
```

### Method 2: Browser Console (User-Facing)

```javascript
// Open DevTools (F12), paste in Console:

// See current cache stats
window.__cacheStats && window.__cacheStats();

// Force cache clear and refresh
window.dispatchEvent(new CustomEvent('cache-invalidated', { detail: { scope: 'all' } }));

// Wait 2-3 seconds, then hard refresh
location.reload(true);
```

### Method 3: API Endpoint (Admin)

Create an admin-only cache invalidation endpoint:

```python
@router.post("/admin/cache/invalidate")
async def invalidate_cache(
    user_id: Optional[int] = None,
    scope: str = "all",
    current_user: User = Depends(get_current_super_admin)
):
    """Manually trigger cache invalidation (admin only)."""
    from app.services.redis_cache_service import redis_cache

    if user_id:
        if scope == "all":
            redis_cache.invalidate_all_for_user(user_id)
        elif scope == "files":
            redis_cache.invalidate_user_files(user_id)
        # ... other scopes

        # Notify frontend
        await send_notification(
            user_id=user_id,
            notification_type='cache_invalidate',
            data={'scope': scope}
        )

        return {"status": "ok", "message": f"Invalidated {scope} cache for user {user_id}"}

    return {"status": "ok", "message": "Cache invalidated"}
```

---

## Cache TTLs

**Backend Redis:**
- Tags: 5 minutes
- Speakers: 5 minutes
- Metadata: 5 minutes
- Files: 2 minutes
- Status: 1 minute

**Frontend In-Memory:**
- Tags: 5 minutes
- Speakers: 5 minutes
- Metadata: 5 minutes
- Files: 2 minutes
- Status: **60 seconds** (shortest - updates frequently)

**Note:** Status cache is intentionally short because file status changes frequently during processing.

---

## Automatic Invalidation (Normal Code Path)

These service methods automatically invalidate cache:

**File Operations:**
- `create_media_file()` → invalidates files, status
- `update_media_file_status()` → invalidates files, status
- `delete_media_file()` → invalidates files, status, tags, speakers

**Tag Operations:**
- `add_tag()` → invalidates tags
- `remove_tag()` → invalidates tags

**Speaker Operations:**
- `update_speaker()` → invalidates speakers
- `merge_speakers()` → invalidates speakers

**Always use service layer methods** instead of direct database updates to ensure cache invalidation happens automatically.

---

## Debugging Cache Issues

### Check Redis Cache

```bash
# See all cache keys
docker exec opentranscribe-redis redis-cli -a "PASSWORD" KEYS "cache:*"

# Clear all cache (nuclear option)
docker exec opentranscribe-redis redis-cli -a "PASSWORD" DEL $(docker exec opentranscribe-redis redis-cli -a "PASSWORD" KEYS "cache:*")
```

### Check Frontend Cache

```javascript
// Browser console
window.__cacheStats && window.__cacheStats();
// Output: Cache: 5 entries, 23 hits, 12 misses (65.7%)
```

### Force Fresh API Call

```javascript
// Browser console - bypass cache completely
fetch('/api/my-files/status', {
  headers: {
    'Authorization': `Bearer ${localStorage.getItem('token')}`,
    'Cache-Control': 'no-cache'
  }
}).then(r => r.json()).then(console.log);
```

---

## Common Scenarios

### Scenario 1: Bulk Status Update Script

```python
# Bad - cache not invalidated
for file in files:
    file.status = FileStatus.ERROR
db.commit()

# Good - cache invalidated
from app.utils.task_utils import update_media_file_status
for file in files:
    update_media_file_status(db, file.id, FileStatus.ERROR)
```

### Scenario 2: Manual Database Fix

```python
# After direct SQL changes
from app.services.redis_cache_service import redis_cache
redis_cache.invalidate_all_for_user(1)  # User 1

# Send WebSocket notification
import asyncio
from app.api.websockets import send_notification

asyncio.run(send_notification(
    user_id=1,
    notification_type='cache_invalidate',
    data={'scope': 'all'}
))
```

### Scenario 3: Frontend Shows Stale Data

**User reports:** "I deleted a file but it still shows in the list"

**Quick fix:**
1. Open DevTools (F12)
2. Run: `window.dispatchEvent(new CustomEvent('cache-invalidated', { detail: { scope: 'all' } }));`
3. Wait 2 seconds
4. Hard refresh (Ctrl+Shift+R)

**Permanent fix:** Find why the delete operation didn't invalidate cache (check service layer).

---

## Best Practices

1. ✅ **Use service layer methods** - They handle cache invalidation automatically
2. ✅ **After direct DB changes** - Always manually invalidate cache
3. ✅ **Test cache behavior** - Verify invalidation works for new features
4. ❌ **Don't rely on TTL alone** - Actively invalidate when data changes
5. ❌ **Don't clear entire Redis** - Use scoped invalidation (user_id specific)
