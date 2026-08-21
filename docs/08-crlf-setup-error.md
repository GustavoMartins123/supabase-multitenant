# Script execution error (.sh) - CRLF / $'\r': command not found

## Description

This error occurs when running `.sh` scripts in Linux environments if the files were created or edited on Windows.

---

## Symptom

When running the script:

```bash
sudo bash setup.sh
```

Errors such as:

```bash
$'\r': command not found
: invalid option: set: -
syntax error near unexpected token `$'{\r''
```

---

## Cause

The `.sh` file uses **CRLF (Windows)** line endings, while Linux uses **LF (Unix)**.

The `\r` (carriage return) character is interpreted as invalid by the shell, causing execution errors.

---

## Diagnosis

Check the file format:

```bash
file setup.sh
```

If it shows:

```
with CRLF line terminators
```

---

### Convert all project scripts and environments

```bash
find . -type f \( -name "*.sh" -o -name ".env*" \) -exec sed -i 's/\r$//' {} +
```

---

### Convert a single file

```bash
sed -i 's/\r$//' setup.sh
```

---

## Test again

```bash
sudo bash setup.sh
```

---

## 📅 Last updated

March 2026
