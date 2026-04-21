# Security Audit — Deep Reference

Security review checklist specifically for Elixir/Phoenix/Ecto code. Used when auditing for common vulnerabilities.

**Scope:** OWASP Top-10-relevant patterns, BEAM-specific issues (atom exhaustion, code injection via macros), and Phoenix/Ecto-specific pitfalls. Does **not** cover network-level, infra, or dependency-vulnerability scanning (use `mix deps.audit` / `sobelow` for that).

**Use with `sobelow`:** `mix sobelow` provides automated scans — this doc covers the judgment calls sobelow can't make.

---

## Rules for Security Review

1. **ALWAYS validate at the system boundary.** Untrusted input is anywhere data crosses into your process: HTTP, queue consumers, file reads, external APIs, MCP/JSON inputs.
2. **NEVER call `String.to_atom/1` on user input.** Use `String.to_existing_atom/1` or explicit whitelists.
3. **NEVER call `:erlang.binary_to_term/1` without `[:safe]`** on untrusted data.
4. **ALWAYS parameterize Ecto queries.** Never interpolate user input into `fragment("...")` or raw SQL.
5. **ALWAYS check authorization at the context boundary.** Controllers/LiveViews set up the request; contexts enforce rules.
6. **NEVER log secrets.** Use `redact: true` on schema fields; scrub params in Plug.Logger and in your own log statements.
7. **ALWAYS rate-limit expensive operations.** Login, password reset, email send, crypto operations need throttling.
8. **ALWAYS use constant-time comparison for secrets.** `Plug.Crypto.secure_compare/2` for token/HMAC comparison — never `==`.
9. **NEVER trust `remote_ip` without a trusted proxy list.** X-Forwarded-For is user-controlled unless you've configured your Plug chain to only accept it from known proxies.
10. **ALWAYS scope queries to the authorized user.** `Repo.get!(Post, id)` is broken if the post belongs to someone else — always include `where: p.user_id == ^current_user.id`.

---

## Input Validation & Injection

### Atom-table injection (DoS)

Atoms are not garbage collected. Limit defaults to ~1M. Unbounded atom creation exhausts the table and crashes the node.

```elixir
# BAD
def handle_event(type, data), do: do_work(String.to_atom(type))

# GOOD
@allowed_types ~w(login signup logout)
def handle_event(type, data) when type in @allowed_types,
  do: do_work(String.to_existing_atom(type))
def handle_event(_type, _data), do: :error
```

Also in JSON decoding:

```elixir
# BAD — every distinct JSON key becomes an atom
Jason.decode!(body, keys: :atoms)

# GOOD
Jason.decode!(body)                    # Keep as strings
# OR
Jason.decode!(body, keys: :atoms!)    # Raise on unknown atoms
```

### SQL injection via `fragment`

```elixir
# BAD — user input interpolated
from(u in User, where: fragment("name = '#{q}'"))

# GOOD — parameterize
from(u in User, where: fragment("name = ?", ^q))
# OR stay in Ecto DSL
from(u in User, where: u.name == ^q)
```

### Code injection via `Code.eval_string`

```elixir
# BAD
{result, _} = Code.eval_string(user_input)

# GOOD — never eval user input; use a safe expression evaluator or a constrained DSL
```

### Binary-to-term without `:safe`

```elixir
# BAD — untrusted binary; can allocate atoms, refs
:erlang.binary_to_term(network_input)

# GOOD
:erlang.binary_to_term(network_input, [:safe])
```

### Command injection

```elixir
# BAD
System.cmd("sh", ["-c", "cat #{user_file}"])

# GOOD
System.cmd("cat", [user_file])           # No shell, no interpolation
# Still validate: reject ".." paths, absolute paths outside base dir
```

### Path traversal

```elixir
# BAD
File.read!("uploads/#{filename}")      # filename = "../../../etc/passwd"

# GOOD
base = "uploads/"
path = Path.join(base, filename)
if String.starts_with?(Path.expand(path), Path.expand(base)),
  do: File.read(path),
  else: {:error, :invalid_path}
```

### ReDoS (regex denial of service)

```elixir
# BAD — catastrophic backtracking for adversarial inputs
Regex.match?(~r/(a+)+$/, user_input)

# GOOD — use simpler pattern, length-limit input, or use re2
if byte_size(user_input) < 100, do: Regex.match?(~r/^a+$/, user_input)
```

---

## Authentication & Session Security

### Password hashing

```elixir
# BAD — fast hashes
:crypto.hash(:sha256, password)
Bcrypt.hash_pwd_salt(password, log_rounds: 4)    # Too low

# GOOD
Bcrypt.hash_pwd_salt(password)                    # default work factor (12+)
Argon2.hash_pwd_salt(password)                    # preferred if available
```

### Constant-time comparison for secrets

```elixir
# BAD — timing attack
if stored_token == provided_token, do: :ok

# GOOD
if Plug.Crypto.secure_compare(stored_token, provided_token), do: :ok
```

### Session token handling

- Store tokens in `httpOnly`, `secure`, `same_site: :lax` cookies.
- For API tokens: hash at rest (store SHA-256 of token; send plaintext to user only once).
- Rotate on login; invalidate on logout.
- Use `Plug.Session` with cookie encryption (Phoenix default).

```elixir
# Phoenix session config
config :my_app, MyAppWeb.Endpoint,
  session: [
    store: :cookie,
    key: "_my_app_key",
    signing_salt: "...",
    encryption_salt: "...",
    same_site: "Lax",
    secure: true,
    http_only: true
  ]
```

### CSRF

Phoenix enables `Plug.CSRFProtection` by default. Audit:

```elixir
# router.ex
pipeline :browser do
  plug :accepts, ["html"]
  plug :fetch_session
  plug :fetch_live_flash
  plug :protect_from_forgery        # ← required; do not remove
  plug :put_secure_browser_headers
end
```

For JSON APIs, token-based auth bypasses CSRF — but only if the API never reads session cookies for auth. If your API falls back to cookie-based session auth, CSRF protection is still needed.

### Rate limiting

Expensive operations — login, password reset, signup, email send — must be rate-limited.

```elixir
# With Hammer
defmodule MyAppWeb.LoginController do
  def create(conn, %{"email" => email, "password" => pwd}) do
    case Hammer.check_rate("login:#{email}", 60_000, 5) do   # 5 per minute
      {:allow, _} -> authenticate(conn, email, pwd)
      {:deny, _} -> conn |> put_status(429) |> json(%{error: "too many attempts"})
    end
  end
end
```

---

## Authorization

### Always scope queries to the current user

```elixir
# BAD — IDOR (Insecure Direct Object Reference)
def show(conn, %{"id" => id}) do
  post = Repo.get!(Post, id)        # ANY post, not just user's
  render(conn, :show, post: post)
end

# GOOD
def show(conn, %{"id" => id}) do
  post =
    Post
    |> where(user_id: ^conn.assigns.current_user.id)
    |> Repo.get!(id)
  render(conn, :show, post: post)
end

# BEST — in the context
def get_user_post!(user, id) do
  Post
  |> where(user_id: ^user.id)
  |> Repo.get!(id)
end
```

### Role checks at context boundary

```elixir
# BAD — controller does it; inconsistent
def update(conn, params) do
  if conn.assigns.current_user.role == :admin, do: do_update(params), else: forbidden(conn)
end

# GOOD — context enforces it
def update_post(user, post_id, params) do
  post = get_post!(post_id)
  if User.admin?(user) or post.user_id == user.id do
    # ...
  else
    {:error, :unauthorized}
  end
end
```

### Don't leak permission info through error messages

```elixir
# BAD — different messages reveal existence
def get_post(user, id) do
  case Repo.get(Post, id) do
    nil -> {:error, :not_found}
    %{user_id: uid} when uid != user.id -> {:error, :forbidden}
    post -> {:ok, post}
  end
end

# GOOD — same response for both
def get_post(user, id) do
  Post
  |> where([p], p.id == ^id and p.user_id == ^user.id)
  |> Repo.one()
  |> case do
    nil -> {:error, :not_found}
    post -> {:ok, post}
  end
end
```

### Mass assignment

Always whitelist fields in changesets:

```elixir
# BAD — user can set role to :admin
def changeset(user, attrs), do: cast(user, attrs, Map.keys(attrs))

# GOOD
@user_fields ~w(email name password)a    # role NOT included
def registration_changeset(user, attrs), do: cast(user, attrs, @user_fields)

@admin_fields ~w(email name role)a        # role included
def admin_changeset(user, attrs), do: cast(user, attrs, @admin_fields)
```

---

## Logging & Secret Exposure

### Redact sensitive fields

```elixir
schema "users" do
  field :email, :string
  field :hashed_password, :string, redact: true
  field :password, :string, virtual: true, redact: true
  # ...
end
```

`redact: true` hides the field from `inspect/2`, which means Logger won't print it.

### Scrub parameters in Plug.Logger

```elixir
# endpoint.ex
plug Plug.Parsers,
  parsers: [:urlencoded, :multipart, :json],
  json_decoder: Phoenix.json_library()

plug Plug.Logger  # Phoenix default — logs params at :info

# In dev.exs / prod.exs filter:
config :phoenix, :filter_parameters, ["password", "token", "secret", "api_key"]
```

### Scrub your own log statements

```elixir
# BAD
Logger.info("User logged in: #{inspect(user)}")    # user may include hashed_password

# GOOD — log only the fields you need
Logger.info("User logged in: #{user.email}")

# GOOD — struct-level redaction via @derive Inspect (inspect/2 honors it)
defmodule User do
  @derive {Inspect, except: [:hashed_password, :api_key]}
  defstruct [:email, :name, :hashed_password, :api_key]
end
# Logger.info("User: #{inspect(%User{...})}")
# → %User{email: "...", name: "...", hashed_password: #Inspect.Opaque<...>}
```

### Environment variables

- Never commit `.env` or `config/prod.secret.exs`.
- Use `System.fetch_env!/1` for required secrets (raises on missing → fails fast).
- Use releases' `config/runtime.exs` — loaded at boot time from env vars.

```elixir
# config/runtime.exs
if config_env() == :prod do
  secret_key_base =
    System.get_env("SECRET_KEY_BASE") ||
      raise "SECRET_KEY_BASE is missing"
end
```

---

## Crypto Pitfalls

### `:crypto` — Which Primitive?

| When you need to... | Use | NOT |
|---|---|---|
| Hash a password | `Bcrypt.hash_pwd_salt/1` or `Argon2.hash_pwd_salt/1` | `:crypto.hash(:sha256, ...)` — too fast, brute-forceable |
| Generic message digest (checksum, content hash) | `:crypto.hash(:sha256, data)` or `:crypto.hash(:blake2b, data)` | MD5, SHA1 (broken) |
| HMAC (authenticated message) | `:crypto.mac(:hmac, :sha256, key, data)` | Plain hash + concat (length-extension attack) |
| Encrypt + authenticate (at rest or in transit) | AEAD: `:crypto.crypto_one_time_aead(:aes_256_gcm, key, iv, pt, aad, true)` | Plain `:aes_256_cbc` (no authentication) |
| Encrypt a Phoenix session/token | `Phoenix.Token.encrypt/3` | Hand-rolled AES |
| Sign (non-repudiation, public verify) | `:public_key.sign/3` with `:ecdsa` or `:rsa` | HMAC (HMAC is symmetric; can't be publicly verified) |
| Random bytes / ID / salt | `:crypto.strong_rand_bytes/1` | `:rand.uniform` (predictable PRNG) |
| Random URL-safe token | `:crypto.strong_rand_bytes(32) \|> Base.url_encode64(padding: false)` | `System.unique_integer()` |
| Key agreement (ECDH) | `:crypto.generate_key(:ecdh, :x25519)` + `:crypto.compute_key(:ecdh, ...)` | Roll-your-own DH |
| Derive a key from a password | `:crypto.pbkdf2_hmac(:sha256, pwd, salt, iters, len)` or `Argon2` | Raw hash of password |
| Derive multiple keys from one master key | HKDF via `hkdf_erlang` / `ex_hkdf` libraries, or hand-rolled HKDF-Expand using `:crypto.mac/4` (HMAC-SHA256) | Concatenating SHA outputs |
| Constant-time equality (token / HMAC compare) | `Plug.Crypto.secure_compare/2` | `==` (timing attack) |

**Rules of thumb:**

- **Never hash a password with `:crypto.hash`.** Use Bcrypt or Argon2 — they're designed to be slow.
- **Always use AEAD** (authenticated encryption) for confidentiality. Plain CBC/CTR lets attackers tamper silently.
- **IV / nonce uniqueness matters.** `:crypto.strong_rand_bytes(12)` for GCM nonces. Never reuse a `(key, iv)` pair for AEAD.
- **Store the IV / salt alongside the ciphertext.** They're not secret; they must be retrievable.

### Symmetric encryption (AEAD) — recipe

```elixir
def encrypt(plaintext, key) when byte_size(key) == 32 do
  iv = :crypto.strong_rand_bytes(12)
  {ciphertext, tag} =
    :crypto.crypto_one_time_aead(:aes_256_gcm, key, iv, plaintext, "", true)
  # Store iv <> tag <> ciphertext (iv and tag are not secret)
  iv <> tag <> ciphertext
end

def decrypt(<<iv::binary-12, tag::binary-16, ciphertext::binary>>, key)
    when byte_size(key) == 32 do
  case :crypto.crypto_one_time_aead(:aes_256_gcm, key, iv, ciphertext, "", tag, false) do
    :error -> {:error, :invalid_ciphertext_or_key}
    pt -> {:ok, pt}
  end
end
```

### HMAC recipe

```elixir
def sign(data, secret) do
  :crypto.mac(:hmac, :sha256, secret, data)
end

def verify(data, mac, secret) do
  expected = :crypto.mac(:hmac, :sha256, secret, data)
  Plug.Crypto.secure_compare(expected, mac)   # constant-time!
end
```

### ECDH key agreement recipe

```elixir
# Alice generates keypair
{alice_pub, alice_priv} = :crypto.generate_key(:ecdh, :x25519)

# Bob generates keypair
{bob_pub, bob_priv} = :crypto.generate_key(:ecdh, :x25519)

# Both compute the same shared secret
shared_a = :crypto.compute_key(:ecdh, bob_pub, alice_priv, :x25519)
shared_b = :crypto.compute_key(:ecdh, alice_pub, bob_priv, :x25519)
# shared_a == shared_b

# Derive a usable key via HKDF — Erlang's :crypto has no built-in HKDF;
# use the `hkdf_erlang` hex package, or hand-roll HKDF-Expand with HMAC-SHA256:
key = hkdf_expand(shared_a, "my-app-v1", 32)

defp hkdf_expand(prk, info, len) do
  # RFC 5869 HKDF-Expand (simplified — omits the Extract step for ECDH output)
  :crypto.mac(:hmac, :sha256, prk, info <> <<1>>)
  |> binary_part(0, len)
end
```

### Key derivation (PBKDF2 — legacy; prefer Argon2)

```elixir
# For derivation from a password (use Argon2 for new designs)
salt = :crypto.strong_rand_bytes(16)
key = :crypto.pbkdf2_hmac(:sha256, password, salt, 600_000, 32)
# Store: salt <> key in your DB
```

### Use `:crypto.strong_rand_bytes/1` for secrets

```elixir
# BAD — predictable
:rand.uniform()

# GOOD
:crypto.strong_rand_bytes(32) |> Base.url_encode64(padding: false)
```

### Don't roll your own crypto

```elixir
# BAD — vulnerable to many attacks
token = :crypto.hash(:sha256, user_id <> secret)

# GOOD — use Phoenix.Token (encrypted + signed + expiry)
token = Phoenix.Token.sign(endpoint, "user-id", user.id)
# Later:
Phoenix.Token.verify(endpoint, "user-id", token, max_age: 86400)
```

### TLS configuration

Always verify peer certs on clients:

```elixir
# BAD — MITM risk
:ssl.connect(~c"api.example.com", 443, [verify: :verify_none])

# GOOD
:ssl.connect(~c"api.example.com", 443, [
  verify: :verify_peer,
  cacerts: :public_key.cacerts_get(),
  server_name_indication: ~c"api.example.com",
  customize_hostname_check: [match_fun: :public_key.pkix_verify_hostname_match_fun(:https)]
])
```

With Req/Finch:

```elixir
Req.get!(url, connect_options: [transport_opts: [verify: :verify_peer, cacerts: :public_key.cacerts_get()]])
```

---

## Phoenix-Specific

### CSP headers

```elixir
plug :put_secure_browser_headers, %{
  "content-security-policy" => "default-src 'self'; ..."
}
```

### Host header injection

`Phoenix.Router` uses the Host header by default in `url_for`. If an attacker controls the Host, they can create phishing-style password reset links.

```elixir
# endpoint.ex — for prod
config :my_app, MyAppWeb.Endpoint,
  url: [host: "myapp.com", port: 443, scheme: "https"]

# Check: are links generated with config host? Or conn-derived host?
Routes.user_url(MyAppWeb.Endpoint, :show, user)        # Uses config — GOOD
Routes.user_url(conn, :show, user)                      # Uses conn.host — vulnerable if not vetted
```

### Open redirect

```elixir
# BAD
def after_login(conn, %{"return_to" => url}) do
  redirect(conn, external: url)
end

# GOOD — validate URL is internal
def after_login(conn, %{"return_to" => url}) do
  if internal?(url), do: redirect(conn, to: url), else: redirect(conn, to: ~p"/home")
end

defp internal?(url), do: String.starts_with?(url, "/") and not String.starts_with?(url, "//")
```

### XSS via raw HTML

```elixir
# BAD — HEEx allows raw output
~H"""
<%= raw @user_input %>
"""

# GOOD — HEEx escapes by default
~H"""
<%= @user_input %>
"""
# Only use `raw/1` on trusted content (your own templates, sanitized markup)
```

### File uploads

- Validate MIME type (`Plug.Upload` provides `content_type` but it's user-supplied — re-sniff).
- Validate file size at the Plug layer (`Plug.Parsers` has `:length`).
- Don't serve uploads from the same origin (use separate domain or signed URLs).
- Store outside the app directory.

```elixir
plug Plug.Parsers,
  parsers: [:urlencoded, :multipart, :json],
  length: 10_000_000,      # 10 MB max
  json_decoder: Phoenix.json_library()
```

### Unbounded allocation

```elixir
# BAD
{:ok, body, _} = Plug.Conn.read_body(conn)     # default unlimited? Actually 8MB default

# GOOD — explicit limit
{:ok, body, conn} = Plug.Conn.read_body(conn, length: 1_000_000)
```

---

## Ecto-Specific

### Raw SQL

```elixir
# BAD — interpolation
Ecto.Adapters.SQL.query(Repo, "SELECT * FROM users WHERE email = '#{email}'")

# GOOD — parameterize
Ecto.Adapters.SQL.query(Repo, "SELECT * FROM users WHERE email = $1", [email])
```

### Query injection via keyword list

```elixir
# BAD — order_by: direction is an atom, if sourced from user input → atom injection
direction = String.to_atom(params["dir"])          # attacker: "asc; DROP TABLE..." → atom
from(u in User, order_by: [{^direction, u.email}])
```

```elixir
# GOOD — whitelist
direction = if params["dir"] == "desc", do: :desc, else: :asc
from(u in User, order_by: [{^direction, u.email}])
```

### Updates without WHERE

```elixir
# BAD — accidentally updates all rows
Repo.update_all(User, set: [active?: true])

# GOOD — scoped
from(u in User, where: u.org_id == ^org_id)
|> Repo.update_all(set: [active?: true])
```

### Multi-tenancy leakage

If using row-level tenancy (`tenant_id` column), ensure EVERY query filters by tenant:

```elixir
# BAD — cross-tenant leak
def list_posts, do: Repo.all(Post)

# GOOD
def list_posts(tenant), do: Repo.all(from(p in Post, where: p.tenant_id == ^tenant.id))
```

Consider enforcing via a `Repo.prepare_query/3` callback that injects tenant filter, or use Postgres row-level security.

---

## Dependency Security

### Check for vulnerable deps

```sh
mix hex.audit                  # flags deprecated/retired Hex packages
mix deps.audit                 # requires :mix_audit dep
mix sobelow                    # Phoenix-specific
```

### Pin deps & lock file

- Commit `mix.lock` — recreates same dep versions.
- Use `~>` with major.minor locked for stability.
- Review dep licenses if shipping proprietary.

### Supply chain

- Prefer Hex packages over `git` deps (Hex packages are signed).
- Review new deps before adding — Elixir community is small, a malicious package is significant.

---

## Operational

### Don't expose `:observer` / remote shell

Remote shell (`iex --remsh`) gives full node access. Only allow via SSH tunnel or from a bastion.

### Disable distribution unless needed

If the app doesn't need node clustering, don't enable it. `:distribution` open port = attack surface.

### Secrets in releases

Never bake secrets into release tarballs. Use `runtime.exs` to read env vars at boot, or a secret store (Vault, AWS Secrets Manager).

### Memory-pressure DoS

Unbounded uploads, unbounded message queues, unbounded ETS growth — all DoS vectors. Set hard limits:

- `Plug.Parsers` `length:` option
- GenServer mailbox monitoring + `max_heap_size`:

```elixir
@impl true
def init(opts) do
  Process.flag(:max_heap_size, %{size: 10_000_000, kill: true, error_logger: true})
  {:ok, opts}
end
```

---

## Audit Checklist Summary

When reviewing a PR, quickly scan for:

- [ ] `String.to_atom` / `keys: :atoms` on user input
- [ ] `:erlang.binary_to_term` without `:safe`
- [ ] `fragment("... #{var}")` interpolation
- [ ] Queries without tenant/user scope
- [ ] `cast(_, _, Map.keys(attrs))` — mass assignment
- [ ] `== ` for token comparison → use `Plug.Crypto.secure_compare`
- [ ] Plaintext secrets in logs / not `redact: true`
- [ ] Missing rate limits on login/reset/signup
- [ ] Unrestricted file upload size or path
- [ ] `redirect(external:)` from user input
- [ ] Raw HTML output without sanitization
- [ ] Missing `cacerts` in outbound TLS
- [ ] New deps not in `mix.lock` or from untrusted source
- [ ] `verify: :verify_none` in production code
- [ ] Unbounded `Plug.Conn.read_body`

---

## Cross-References

- **Debugging playbook:** `./debugging-playbook-deep.md`
- **Performance catalog (24 & 25 are also security-relevant):** `./performance-catalog.md`
- **Main reviewing skill §7 Checklists:** `./SKILL.md`
- **Main Elixir security patterns:** `../elixir/architecture-reference.md` (anti-pattern catalog includes several security items)
- **Automated scan:** `mix sobelow --config`
