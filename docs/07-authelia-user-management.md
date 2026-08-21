# Authelia user management

This guide explains how to manage system users with Authelia.

---

## Overview

Authelia handles authentication for all users who access Studio. There are two ways to manage users:

1. **Through the Studio interface** (recommended) - For admins creating new users
2. **Through the YAML file** (manual) - For initial configuration or troubleshooting

---

## Creating new users

### Method 1: Through the Studio interface (recommended)

If you are a system administrator, you can create new users directly through the interface:

1. Open Studio and log in with an admin account
2. Click the **Admin** button (bottom-right corner)
3. On the administration page, click **"New User"** or **"Create User"**
4. Fill in the details:
   - **Email:** User email (used for login)
   - **Display name:** Name shown in the interface
   - **Password:** User's initial password
   - **Groups:** Select "admin" for an administrator, or leave only "active" for a regular user
5. Click **"Create"**

The user is created automatically and can log in immediately.

### Method 2: Through the YAML file (manual)

To create users manually or perform the initial configuration, edit Authelia's user file.

#### Step 1: Generate a password hash

First, generate the password hash with argon2:

```bash
echo -n "user_password" | argon2 $(openssl rand -base64 32) -id -t 3 -m 16 -p 4 -l 32 -e
```

This generates a string such as:
```
$argon2id$v=19$m=65536,t=3,p=4$W4CGddhkzRo9cARHsxdoPA$ly9FEn7cp3lzPsDtCz6JqTIm9XvVpTwVoHKyV4jTjTs
```

#### Step 2: Edit the user file

Open Authelia's user file:

```bash
nano studio/authelia/users_database.yml
```

#### Step 3: Add the new user

Add the user structure to the file. Example for a regular user:

```yaml
joao:
  middle_name: ''
  family_name: ''
  nickname: ''
  gender: ''
  birthdate: ''
  website: ''
  profile: ''
  picture: ''
  zoneinfo: ''
  locale: ''
  phone_number: ''
  password: $argon2id$v=19$m=65536,t=3,p=4$W4CGddhkzRo9cARHsxdoPA$ly9FEn7cp3lzPsDtCz6JqTIm9XvVpTwVoHKyV4jTjTs
  disabled: false
  extra:
    created_at: ts:2026-03-16T18:30:22Z
  given_name: ''
  address: ~
  groups:
    - active
  email: joao@example.com
  phone_extension: ''
  displayname: joao
```

**Important fields:**
- **joao:** Username used for login (must be unique)
- **password:** Hash generated in step 1
- **email:** User email
- **displayname:** Name shown in the interface
- **groups:** Group list (always include "active")
- **disabled:** `false` for active, `true` for disabled
- **created_at:** Creation date (ISO 8601 format with the `ts:` prefix)

#### Step 4: Save and wait

After saving the file, **no container restart is required**. The system updates automatically:

- **Authelia:** Detects file changes through a file watcher and reloads automatically
- **Nginx:** Updates the user cache every 10 seconds

The user will be available to log in within 10 seconds.

---

## Groups and permissions

### User types

There are two types of users in the system:

#### 1. Regular user (group: `active`)

```yaml
groups:
  - active
```

**Permissions:**
- View their own projects
- Create new projects
- Duplicate their projects
- Manage members of their projects
- Start/stop/restart their projects
- Cannot access other users' projects (unless added as a member)
- Cannot delete projects
- Cannot manage system users
- Cannot transfer projects

#### 2. Administrator (groups: `active` + `admin`)

```yaml
groups:
  - active
  - admin
```

**Permissions:**
- All regular-user permissions
- Create and disable system users
- Manage ALL projects (belonging to any user)
- Stop/start/restart any project
- Transfer projects between users
- Delete any project
- Access the administration panel

### Admin user example

```yaml
admin_user:
  middle_name: ''
  family_name: ''
  nickname: ''
  gender: ''
  birthdate: ''
  website: ''
  profile: ''
  picture: ''
  zoneinfo: ''
  locale: ''
  phone_number: ''
  password: $argon2id$v=19$m=65536,t=3,p=4$W4CGddhkzRo9cARHsxdoPA$ly9FEn7cp3lzPsDtCz6JqTIm9XvVpTwVoHKyV4jTjTs
  disabled: false
  extra:
    created_at: ts:2025-07-04T13:19:01Z
  given_name: ''
  address: ~
  groups:
    - active
    - admin
  email: admin@example.com
  phone_extension: ''
  displayname: Administrator
```

**Important:** To make a user an admin, add `admin` to the group list. To remove admin privileges, remove `admin` from the list (leaving only `active`).

---

## Reset a user password

### Method 1: Automatic reset by email (recommended)

If you configured SMTP in Authelia (see [SMTP configuration](#smtp-configuration)), users can reset their own passwords:

1. On the Authelia login screen, click **"Forgot my password"**
2. Enter the registered email
3. The user receives an email with a password-reset link
4. Click the link and set a new password

### Method 2: Manual reset through YAML

If SMTP is not configured or you need to reset manually:

1. Generate a new password hash:
   ```bash
   echo -n "new_password" | argon2 $(openssl rand -base64 32) -id -t 3 -m 16 -p 4 -l 32 -e
   ```

2. Edit the user file:
   ```bash
   sudo nano studio/authelia/users_database.yml
   ```

3. Replace the user's `password` field with the new hash:
   ```yaml
   user:
     password: $argon2id$v=19$m=65536,t=3,p=4$NEW_HASH_HERE
     # ... remaining fields
   ```

4. Save the file. Authelia detects the change automatically.

5. The user can log in with the new password within 10 seconds.

---

## Disable/enable users

### Through the interface (admin)

1. Open the administration panel
2. Find the user in the list
3. Click **"Disable"** or **"Enable"**

### Through YAML

Edit `studio/authelia/users_database.yml` and change the `disabled` field:

```yaml
usuario:
  disabled: true
```

Disabled users cannot log in, but their data is preserved.

---

## SMTP configuration

To enable password resets by email, adjust the `studio/authelia/configuration.yml.template` template and regenerate the local `configuration.runtime.yml` file:

```yaml
notifier:
  smtp:
    host: smtp.gmail.com
    port: 587
    username: your_email@gmail.com
    password: your_app_password
    sender: noreply@yourdomain.com
    identifier: localhost
    subject: "[Supabase] {title}"
    startup_check_address: test@authelia.com
    disable_require_tls: false
    disable_html_emails: false
```

**Gmail note:**
- You need to generate an "App password" in Google's security settings
- Do not use your regular Gmail password
- Enable two-step verification first

After configuring it, restart Authelia:

```bash
docker restart authelia
```

---

## Complete users_database.yml structure

Example of a complete file with multiple users:

```yaml
# Admin user
admin:
  middle_name: ''
  family_name: ''
  nickname: ''
  gender: ''
  birthdate: ''
  website: ''
  profile: ''
  picture: ''
  zoneinfo: ''
  locale: ''
  phone_number: ''
  password: $argon2id$v=19$m=65536,t=3,p=4$HASH_HERE
  disabled: false
  extra:
    created_at: ts:2025-07-04T13:19:01Z
  given_name: ''
  address: ~
  groups:
    - active
    - admin
  email: admin@example.com
  phone_extension: ''
  displayname: Administrator

# Regular user
joao:
  middle_name: ''
  family_name: ''
  nickname: ''
  gender: ''
  birthdate: ''
  website: ''
  profile: ''
  picture: ''
  zoneinfo: ''
  locale: ''
  phone_number: ''
  password: $argon2id$v=19$m=65536,t=3,p=4$HASH_HERE
  disabled: false
  extra:
    created_at: ts:2026-03-16T18:30:22Z
  given_name: ''
  address: ~
  groups:
    - active
  email: joao@example.com
  phone_extension: ''
  displayname: João Silva

# Disabled user
maria:
  middle_name: ''
  family_name: ''
  nickname: ''
  gender: ''
  birthdate: ''
  website: ''
  profile: ''
  picture: ''
  zoneinfo: ''
  locale: ''
  phone_number: ''
  password: $argon2id$v=19$m=65536,t=3,p=4$HASH_AQUI
  disabled: true
  extra:
    created_at: ts:2025-08-15T10:00:00Z
  given_name: ''
  address: ~
  groups:
    - active
  email: maria@example.com
  phone_extension: ''
  displayname: Maria Santos
```

---

## Troubleshooting

### User cannot log in

1. **Check whether the user is active:**
   ```yaml
   disabled: false
   ```

2. **Check whether the "active" group is present:**
   ```yaml
   groups:
     - active
   ```

3. **Check the Authelia logs:**
   ```bash
   docker logs authelia
   ```

4. **Test the password hash:**
   ```bash
   # Generate a new hash and replace it in the file
   echo -n "test_password" | argon2 $(openssl rand -base64 32) -id -t 3 -m 16 -p 4 -l 32 -e
   ```

### File changes are not applied

1. **Check the YAML syntax:**
   - Indentation must use spaces (not tabs)
   - Each indentation level = 2 spaces
   - There must be no trailing spaces

2. **Wait up to 10 seconds** for Nginx to update the cache

3. **Check the logs:**
   ```bash
   docker logs authelia
   docker logs nginx
   ```

4. **As a last resort, restart the containers:**
   ```bash
   docker restart authelia
   docker restart nginx
   ```

### Reset email does not arrive

1. **Check the SMTP configuration** in `configuration.runtime.yml`
2. **Check the Authelia logs:**
   ```bash
   docker logs authelia | grep -i smtp
   ```
3. **Test the SMTP connection:**
   ```bash
   docker exec authelia cat /config/configuration.runtime.yml | grep -A 10 smtp
   ```
4. **Check the email's spam folder**

---

## Best practices

### Security

- Use strong passwords (at least 12 characters)
- Limit the number of admins (only those who need it)
- Disable inactive users instead of deleting them (preserves history)
- Configure SMTP to allow password resets
- Back up `users_database.yml` regularly
- Do not share `users_database.yml` (it contains password hashes)

### Organization

- Use real email addresses to facilitate communication
- Use descriptive display names

### Backup

Back up the user file regularly:

```bash
cp studio/authelia/users_database.yml studio/authelia/users_database.yml.backup

cp studio/authelia/users_database.yml studio/authelia/users_database.yml.$(date +%Y%m%d)
```

---

## References

- [Official Authelia documentation](https://www.authelia.com/docs/)
- [Argon2 Password Hashing](https://github.com/P-H-C/phc-winner-argon2)
- [YAML Syntax](https://yaml.org/spec/1.2/spec.html)
