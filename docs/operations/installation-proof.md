# First-administrator installation proof

`configure_studio_runtime.py` (invoked by setup) generates the private mode-0600 file
`studio/secrets/authelia/STUDIO_BOOTSTRAP_TOKEN`. Only the Studio gateway receives
this Docker secret. Read it locally as the installer and enter it into the first-admin
dialog; it is sent in `X-Installation-Token`, never in the URL or browser storage.

The users-database filesystem lock covers proof verification and durable consumption.
The marker `studio/authelia/.studio-bootstrap-consumed` is fsync-persisted before any
account write. The proof is single-use, including concurrent requests and restarts.
Existing accounts (even disabled ones) also close anonymous bootstrap. Deleting accounts
does not reopen an installation that has consumed its proof.

A failure after consuming the proof intentionally leaves bootstrap closed. Recover
locally as the installer: inspect/repair the YAML and control-plane sync, ensure no
account creation succeeded, and only then explicitly remove the consumed marker and
generate a new installation proof. Never automate reopening or publish either file.
