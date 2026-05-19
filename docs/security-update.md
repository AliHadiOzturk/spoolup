# Security Update - Public Server Protection

## ⚠️ CRITICAL: Public Registration Disabled by Default

**Before this update:** Anyone could create an account by visiting `/auth/register`

**After this update:** Registration is disabled by default for public servers

## Security Features Implemented

### 1. Registration Lock (Disabled by Default)

**Default behavior:** `ALLOW_REGISTRATION=false`

Registration is now controlled:
- ✅ **First user** (bootstrap): Always allowed when no users exist
- ❌ **Subsequent users**: Blocked unless `ALLOW_REGISTRATION=true`
- 🔐 **Admin creation**: Existing authenticated users can create new accounts via `POST /api/users`

**Environment Variable:**
```env
# Set to 'true' only if you want open registration (not recommended for public servers)
ALLOW_REGISTRATION=false
```

### 2. Admin Auto-Creation (Recommended for First Setup)

Create admin user automatically on startup:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-very-strong-password-here
```

**How it works:**
1. On startup, checks if admin user exists
2. If not, creates admin with provided credentials
3. If exists, logs "already exists" and continues

**Security note:** Admin credentials are only used once on first startup. Change password after login.

### 3. Login Rate Limiting

**Protection:** Brute force attacks

**Default:** 5 failed attempts within 15 minutes = temporary lock

**Environment Variable:**
```env
MAX_LOGIN_ATTEMPTS=5
```

**How it works:**
- Tracks failed login attempts per username
- Resets after 15 minutes of no attempts
- Returns HTTP 429 (Too Many Requests) when limit reached
- Logs warning for monitoring

### 4. Admin-Only User Creation

When registration is disabled, admins can still create users:

```bash
curl -X POST http://localhost:8000/api/users \
  -H "Authorization: Bearer <your-jwt-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "newuser",
    "password": "securepassword",
    "email": "user@example.com"
  }'
```

## Configuration for Public Servers

### Option 1: Admin-Only (Most Secure)
```env
ALLOW_REGISTRATION=false
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-very-strong-password-here
```

1. Start the server
2. Admin account created automatically
3. Login as admin
4. Create additional users as needed via API
5. Never expose registration to public

### Option 2: Temporary Registration
```env
# Start with registration enabled
ALLOW_REGISTRATION=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-very-strong-password-here
```

1. Start the server
2. Register your account(s)
3. **Immediately disable registration:**
   ```env
   ALLOW_REGISTRATION=false
   ```
4. Restart server
5. Future users must be created by admin

### Option 3: Open Registration (NOT RECOMMENDED)
```env
ALLOW_REGISTRATION=true
# No admin credentials set
```

Anyone can register. Only use this for:
- Local development
- Trusted internal networks
- Demo/testing environments

## Updated Files

### Configuration Files
- `video_management/config/__init__.py` - Added security settings
- `video_management/.env.example` - Added security variables
- `docker-compose.yml` - Added security environment variables

### Application Logic
- `video_management/ui/main.py` - Updated register endpoint with security checks
  - Registration lock after first user
  - Rate limiting on login
  - Admin-only user creation endpoint
  - Auto-admin creation on startup

## API Changes

### Modified Endpoints

**POST /auth/register**
- Now checks `ALLOW_REGISTRATION` setting
- Returns 403 Forbidden if disabled and users exist
- Still allows first user registration (bootstrap)

**POST /auth/login**
- Added rate limiting (5 attempts per 15 minutes)
- Returns 429 Too Many Requests when limit reached
- Tracks failed attempts per username

### New Endpoints

**POST /api/users** (Protected - Admin only)
- Create new users when registration is disabled
- Requires authentication
- Returns 201 Created on success

## Testing Security

### Test Registration Lock
```bash
# First registration should work (no users exist)
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "firstuser", "password": "password123"}'

# Second registration should fail (registration disabled)
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "seconduser", "password": "password123"}'
# Expected: 403 Forbidden
```

### Test Rate Limiting
```bash
# Attempt login 6 times with wrong password
for i in {1..6}; do
  curl -X POST http://localhost:8000/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username": "admin", "password": "wrongpassword"}'
done

# 6th attempt should return 429 Too Many Requests
```

## Migration from Previous Version

If you have an existing database:
1. Update your `.env` file with security settings
2. Restart the server
3. Existing users remain active
4. New registrations blocked (unless enabled)

## Security Checklist for Public Deployment

- [ ] Set `ALLOW_REGISTRATION=false`
- [ ] Set strong `ADMIN_USERNAME` and `ADMIN_PASSWORD`
- [ ] Change default `SECRET_KEY` to random string
- [ ] Use HTTPS (behind reverse proxy)
- [ ] Configure firewall rules
- [ ] Set up log monitoring
- [ ] Regularly update dependencies
- [ ] Enable Docker health checks
- [ ] Use strong passwords for all accounts

## Important Notes

1. **Default behavior is secure**: Registration disabled by default
2. **First user is always allowed**: Even with registration disabled, you can create the first account
3. **Admin auto-creation is optional**: But recommended for convenience
4. **Rate limiting is in-memory**: Resets on server restart (use Redis for persistence in production)
5. **Environment variables are safe**: Credentials are never logged or exposed

## Support

For security issues or questions:
- Review `SECURITY.md` for full security policy
- Check `SECURITY_CHECKLIST.md` before publication
- Never commit `.env` or credential files

---

**Last Updated**: 2026-05-10
**Version**: Security Update 1.0