# Backup setup guide

How to set up the nightly `journal.db` snapshot backup on a fresh server.
The whole thing is one script: run it, answer a few questions, and it
installs a systemd timer, then snapshots your database every night.

Written for a host that runs the Trading Journal backend (SQLite, WAL mode)
under systemd. You **do not** need the `sqlite3` CLI — everything uses
Python's built-in `sqlite3` module.

---

## Quick start

```bash
# from the repo root on the target host
chmod +x backup.sh
./backup.sh          # wizard: Enter accepts defaults
```

The wizard asks:

| Question | Default | Notes |
|---|---|---|
| Database file | `<repo>/backend/journal.db` | |
| Backup directory | `/root/backups` | snapshots land here |
| Keep snapshots for how many days? | 14 | older ones are pruned |
| Install systemd timer? | n | **answer `y`** for automatic backups |
| Backup time (24h, UTC) | `03:30` | after the nightly EOD writes |
| Frequency | `daily` | also `weekly` (Mon) / `monthly` (1st) |

That's it. Settings are saved to `.backup.env` and the systemd units
(`journal-backup.service` / `journal-backup.timer`) are written to
`/etc/systemd/system/` and enabled.

---

## CLI reference

| Command | Does |
|---|---|
| `./backup.sh` | interactive wizard in a terminal; otherwise runs one backup |
| `./backup.sh --backup` | run a single backup now, never prompts |
| `./backup.sh --setup` | force the wizard |
| `./backup.sh --yes` | wizard with all defaults, no questions |
| `./backup.sh --help` | usage |

Every backup run ends by printing where the snapshot was stored and a reminder
to keep an offsite copy of that directory.

---

## Verify (do this once, after setup)

```bash
systemctl list-timers journal-backup.timer
# NEXT                              LEFT       LAST    PASSED    UNIT                  ACTIVATES
# Mon 2026-11-09 03:31:23 UTC      21h        -       -         journal-backup.timer  journal-backup.service

./backup.sh --backup
# OK  stored backup at: /root/backups/journal-2026-11-08.db  (303104 bytes, integrity ok, 1 snapshots kept)
# TIP this file is the only copy of your journal on this host — consider backing it up ...

ls -la /root/backups/
# should show exactly one file per day: journal-YYYY-MM-DD.db (no -wal/-shm sidecars)
```

Also do a **restore drill** once:

```bash
sudo systemctl stop journal-backend
cp /root/backups/journal-2026-11-08.db "$(pwd)/backend/journal.db"
# if old WAL sidecars exist next to the old DB, remove them first:
# rm -f backend/journal.db-wal backend/journal.db-shm
sudo systemctl start journal-backend
# open the app, confirm your data is there
```

---

## Configuration

Settings live in `.backup.env` next to the script (created by the wizard).
They can also be provided as environment variables; environment wins.

| Variable | Default |
|---|---|
| `JOURNAL_DB` | `<repo>/backend/journal.db` |
| `BACKUP_DIR` | `/root/backups` |
| `RETENTION_DAYS` | 14 |
| `BACKUP_TIME` | `03:30` |
| `BACKUP_FREQ` | `daily` |
| `INSTALL_SYSTEMD` | `n` |

The generated service unit runs `backup.sh --backup` with
`EnvironmentFile` pointing at `.backup.env`, so tuning retention or paths
later is just editing that file (no need to re-run the wizard or touch the
units).

---

## Restoring

```bash
sudo systemctl stop journal-backend
cp /root/backups/journal-YYYY-MM-DD.db "$(pwd)/backend/journal.db"
sudo systemctl start journal-backend
```

The snapshots are self-contained single files (normalized out of WAL mode), so
a restore is just copy + restart.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Timer never fires | `systemctl status journal-backup.timer`; `journalctl -u journal-backup.timer` |
| Service fails | `systemctl start journal-backup.service` then `journalctl -u journal-backup.service -n 50` |
| `ERROR: database not found` | set `JOURNAL_DB` in `.backup.env` |
| Snapshot fails integrity check | the script refuses to keep it and exits non-zero; re-run `--backup` |

---

## Partner with Zerobyte (offsite copy)

The timer covers on-host snapshots. For offsite, encrypted copies, point the
[Zerobyte](https://github.com/nicotsx/zerobyte) backup automation on your
backup server at this directory via an SFTP/NFS/SMB source (e.g. SFTP to
`journal:22`, path `/root/backups`), scheduled after 03:30 UTC, with a
retention policy (e.g. 30 daily / 12 monthly). The DB is a few hundred KB, so
storage cost is negligible.
