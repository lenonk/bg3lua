# bg3lua

A small terminal console for the Baldur's Gate 3 Script Extender's Lua
debugger, for Linux/Proton where the in-game console isn't available.

It's a single Python 3 file with no dependencies — it speaks just enough of
BG3SE's protobuf debugger protocol to connect, evaluate Lua, and stream
`print()` / `_D()` output back to your terminal.

```
$ ./bg3lua
Connected to BG3SE Lua debugger (protocol 4).
Context: server.  :server / :client / :expr CODE / :quit
server> Osi.GetHostCharacter()
d94489e2-67d8-2794-45c5-1465fe1469a6
server> _D(Ext.Entity.Get(Osi.GetHostCharacter()).Health)
{
    "Hp": 34,
    "IsInvulnerable": false,
    "MaxHp": 58,
    "MaxTemporaryHp": 0,
    "TemporaryHp": 0
}
```

## Requirements

- Python 3.8+ (no third-party packages)
- BG3 running, with the Script Extender installed
- **`"EnableLuaDebugger": true` in `ScriptExtenderSettings.json`** — see below

### Enabling the debugger

The debugger is off by default. Edit `ScriptExtenderSettings.json`, which on a
Steam/Proton install lives next to the game binary:

```
~/.local/share/Steam/steamapps/common/Baldurs Gate 3/bin/ScriptExtenderSettings.json
```

Add `EnableLuaDebugger`:

```json
{
  "EnableLuaDebugger": true,
  "EnableLogging": true,
  "LogFailedCompile": true,
  "LogRuntime": true
}
```

Create the file if it isn't there. **Restart the game** — the setting is read
at startup. BG3SE then listens on `127.0.0.1:9998`.

To confirm it's listening:

```
ss -ltn 'sport = :9998'
```

## Usage

```
./bg3lua                              # interactive REPL, server context
./bg3lua --client                     # interactive REPL, client context
./bg3lua -e 'Osi.GetHostCharacter()'  # run one line and exit
./bg3lua -x '1+1'                     # evaluate one raw expression and exit
./bg3lua --host 127.0.0.1 --port 9998
```

| Flag | Meaning |
| --- | --- |
| `--host` / `--port` | Debugger address (default `127.0.0.1:9998`) |
| `--client` | Use the client Lua context instead of the server one |
| `-e`, `--execute LUA` | Run one line of Lua and exit |
| `-x`, `--expression LUA` | Evaluate one raw expression and exit |
| `--protocol N` | Debugger protocol to request (default 4; auto-renegotiated) |
| `--traceback` | Show the raw Lua stack traceback on errors |

Exit status is `0` on success, `1` if the Lua errored, `2` if it couldn't
connect.

### Interactive commands

| Command | Meaning |
| --- | --- |
| `:server` | Evaluate in the server context (default) |
| `:client` | Evaluate in the client context |
| `:expr CODE` | Evaluate `CODE` as a raw expression, bypassing the REPL wrapper |
| `=CODE` | Shorthand for `:expr CODE` |
| `:quit`, `:q` | Exit |

Anything else is run as Lua. Arrow-key history and editing work via readline.

## How evaluation works

Input behaves like an ordinary Lua REPL:

```
server> x = 5          -- globals persist across lines (and across runs)
server> x * 2
10
server> local a = 1    -- 'local' is scoped to the line, as in any Lua REPL
server> for i=1,2 do print(i) end
1
2
server> return {a=1}   -- tables are pretty-printed with _D()
{
    "a": 1
}
```

A line that produces a value has it printed automatically — no `=` needed.
Multiple return values are each printed on their own line.

Under the hood this is necessary because **BG3SE ignores the protocol's
`EVAL_AS_STATEMENT` flag**: it always compiles the payload as an expression,
trying `return <code>` and then `local x = <code>`. Sending `x = 5` directly
just yields `unexpected symbol near '='`.

So `bg3lua` hands your text to the game's own `load()` instead — `return
<code>` first to capture a value, falling back to plain `<code>` for
statements. Because `load()` compiles your text as its own top-level chunk,
scoping is correct and error line numbers refer to what you typed:

```
server> local q = 1
        q = q + nil
console:2: attempt to perform arithmetic on a nil value
```

`:expr` / `=` skip that wrapper and send the expression to BG3SE verbatim,
which is occasionally useful for poking at the debugger itself.

### Server vs. client context

BG3's Lua runs in two separate states. `Osi.*` and most gameplay APIs are
server-side; UI and input live client-side. Start in the one you need
(`--client`) or switch mid-session with `:server` / `:client`.

## Troubleshooting

**`cannot connect to 127.0.0.1:9998`**
The game isn't running, or `EnableLuaDebugger` isn't set, or you didn't
restart after setting it.

**`BG3SE did not answer the debugger handshake`**
Almost always another client still holding the slot. BG3SE's debugger server
is *single-client*: it does `accept()`, then a blocking message loop, then
`accept()` again. A second connection sits unanswered in the listen backlog.
Close any other `bg3lua` instance (or Visual Studio Code's BG3 debugger) and
retry. `pgrep -af bg3lua` will find strays.

This is also why `bg3lua` sets `SO_LINGER {on, 0}` and closes with an RST
rather than a graceful FIN — under Wine/Proton a normal close doesn't reliably
wake BG3SE out of `recv()`, and the slot stays wedged. If you write your own
client, do the same, and always close in a `finally`.

**`no reply from BG3SE after 30s; the Lua context is probably not loaded`**
You're at the main menu. BG3SE accepts the connection and completes the
handshake, but silently never answers evaluate requests until a save is
actually loaded. Load a game and retry.

**Output looks wrong / no colour**
Colour is disabled when stdout isn't a TTY, or when `NO_COLOR` is set.

## Notes on the protocol

- Framing is a native little-endian `uint32` holding the *total* packet size,
  including the 4-byte length field itself.
- `frame = -1` on an evaluate request means "global context"; omitting the
  field makes protobuf default it to `0`, which BG3SE reads as stack frame 0.
- Numbers come back as **32-bit floats** (`MsgValue` field 4, wire type 5),
  not doubles — including integer results.
- The extender reports its own protocol version in the connect response, and
  `bg3lua` transparently reconnects with it on a mismatch. Since that costs an
  extra connection to a single-client server, `--protocol` lets you skip the
  round trip if your build differs from the default.
