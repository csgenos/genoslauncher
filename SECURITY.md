# Security Policy

## Supported Versions

Only the latest release of GenosLauncher receives security fixes.

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Report vulnerabilities by emailing the maintainer directly or by opening a
[GitHub Security Advisory](https://github.com/csgenos/genoslauncher/security/advisories/new).

Include:
- A description of the issue and its impact
- Steps to reproduce or a proof-of-concept
- Affected version(s)

You should receive an acknowledgement within 72 hours and a resolution timeline
within 7 days.

## Known Limitations

### Access token visible in process arguments (SX-001)

When launching Minecraft, `minecraft-launcher-lib` passes the Microsoft/Minecraft
access token as a command-line argument (`--accessToken <token>`).  This is the
standard mechanism used by all Java-based Minecraft launchers (including the
official one).

**Impact:** On Linux the token is readable from `/proc/<pid>/cmdline` by any
process running as the same user.  On Windows it is visible in Task Manager
(Command-line column) and via WMI/PowerShell by other processes running as the
same user.  There is no API to pass the token out-of-band to the Minecraft JVM.

**Mitigation:** Tokens are short-lived (≤ 50 minutes) and scoped to Minecraft
only.  GenosLauncher proactively refreshes the token immediately before launch
(`ensure_token_fresh()`).  Ensure you trust other software running under your
user account on the same machine.

### Local privacy model

GenosLauncher is offline-first and stores profile metadata locally so the app can
work without network access. `config.json` may contain non-secret but sensitive
metadata such as local instance paths, saved server addresses, offline usernames,
Microsoft account display names, and launcher preferences. Account tokens and the
CurseForge API key use OS keyring storage where available, with an encrypted
app-local fallback. If you share logs, backups, screenshots, or your application
data directory, review them for local paths, account names, and server addresses.

### Fallback credential encryption key

When the system keyring is unavailable, GenosLauncher stores encrypted
credentials in the application data directory using a Fernet key derived from a
random 32-byte secret stored in `APP_DIR/.fallback_key` (mode 0o600).  If an
attacker gains read access to your user profile they can decrypt stored
credentials.  The recommended mitigation is to ensure the system keyring
(Windows Credential Manager, macOS Keychain, or a `secretservice`-compatible
provider on Linux) is available and functional.
