# Headshot Upload CLI

> **Part 2 — Python Developer Take-Home: Headshot Upload to Salesforce**  
> **Author:** Marimuthu V S  
> **Date:** February 2026  

A command-line tool that uploads JPEG headshot images from a local folder to Salesforce, linking each image to the corresponding Contact record. Built with clean separation of concerns, the **Composite API** for efficient batching, and a comprehensive test suite.

---

## Table of Contents

- [Architecture](#architecture)
- [Upload Flow](#upload-flow)
- [Contact ID Extraction Rule](#contact-id-extraction-rule)
- [Setup Instructions](#setup-instructions)
- [Authentication](#authentication)
- [Usage Examples](#usage-examples)
- [CLI Options](#cli-options)
- [Running Tests](#running-tests)
- [Test Coverage Details](#test-coverage-details)
- [Project Structure](#project-structure)
- [Design Decisions](#design-decisions)
- [Logging](#logging)

---

## Architecture

The project enforces strict **separation of concerns** between two layers, inspired by the Service Layer pattern:

```
┌────────────────────────────────────────────────────────────────────────────┐
│  CLI Layer  (headshot_upload/cli/commands.py)                              │
│  ─ Parses arguments using the Click framework                             │
│  ─ Formats and prints console output (banners, tables, progress bar)      │
│  ─ Catches exceptions and displays user-friendly error messages           │
│  ─ Contains ZERO business logic — delegates entirely to the modules layer │
└────────────────────────┬───────────────────────────────────────────────────┘
                         │ calls
┌────────────────────────▼───────────────────────────────────────────────────┐
│  Modules Layer  (headshot_upload/modules/)                                 │
│                                                                            │
│  config.py           → Loads credentials from environment variables        │
│  auth.py             → OAuth 2.0 authentication (CC + Username-Password)   │
│  scanner.py          → Scans folders, extracts Contact IDs from filenames  │
│  encoder.py          → Base64-encodes image files for API payloads         │
│  salesforce_api.py   → Composite API calls with retry & partial success    │
│  uploader.py         → Orchestrates the full upload workflow               │
│                                                                            │
│  ─ Does NOT import Click                                                   │
│  ─ Does NOT print to console (uses Python logging)                         │
│  ─ Fully reusable outside the CLI (e.g., from another script or service)   │
└────────────────────────────────────────────────────────────────────────────┘
```

**Why this separation matters:** The modules layer can be imported and used by any Python program — a web server, a scheduled job, or another CLI. The CLI is just one thin consumer of the core logic.

---

## Upload Flow

The tool follows a five-step pipeline for each batch of headshots:

```
  ┌──────────┐     ┌──────────┐     ┌───────────────────┐     ┌─────────────────────┐     ┌───────────────────────┐
  │  1. Scan │────▸│ 2. Encode│────▸│ 3. Create         │────▸│ 4. Query            │────▸│ 5. Create             │
  │  Folder  │     │  Base64  │     │    ContentVersions │     │    ContentDocumentIds│     │    ContentDocumentLinks│
  └──────────┘     └──────────┘     └───────────────────┘     └─────────────────────┘     └───────────────────────┘
   scanner.py       encoder.py       salesforce_api.py         salesforce_api.py           salesforce_api.py
```

1. **Scan** — `scanner.py` iterates over the folder, filters for `.jpg`/`.jpeg` files, and extracts 15- or 18-character Salesforce Contact IDs from each filename using a regex pattern.
2. **Encode** — `encoder.py` reads each image file from disk and converts it to a base64-encoded UTF-8 string, ready for the `VersionData` field on ContentVersion.
3. **Create ContentVersions** — `salesforce_api.py` sends batched POST requests via the **Composite API** with `allOrNone: false`. Each sub-request creates a ContentVersion record containing the base64 image data.
4. **Query ContentDocumentIds** — After ContentVersions are created, Salesforce auto-generates a ContentDocument for each. A SOQL query retrieves the `ContentDocumentId` for each `ContentVersion.Id`.
5. **Create ContentDocumentLinks** — A second Composite API call creates `ContentDocumentLink` records, connecting each ContentDocument to its corresponding Contact record with `ShareType: "V"` (Viewer) and `Visibility: "AllUsers"`.

---

## Contact ID Extraction Rule

Filenames must follow this pattern:

```
{ContactId}.jpg
{ContactId}.jpeg
{ContactId}_{description}.jpg
{ContactId}_{description}.jpeg
```

> **Note:** Only `.jpg` and `.jpeg` extensions are supported. Files with `.png`, `.gif`, or other extensions are silently skipped.

**Rules:**

| Requirement | Detail |
|---|---|
| **Position** | Contact ID must be at the **start** of the filename |
| **Prefix** | Must start with `003` (Salesforce Contact key prefix) |
| **Length** | Must be exactly **15** or **18** characters |
| **Characters** | Alphanumeric only (`a-z`, `A-Z`, `0-9`) |
| **Separator** | After the ID, only `_` (underscore) or end-of-name is accepted |
| **Extension** | `.jpg` or `.jpeg` (case-insensitive) |

**Examples:**

| Filename | Valid? | Extracted ID |
|---|---|---|
| `003AB00000Abc1DEFA.jpg` | ✅ | `003AB00000Abc1DEFA` |
| `003AB00000Abc1DEFA_headshot.jpeg` | ✅ | `003AB00000Abc1DEFA` |
| `003AB00000Abc12.jpg` | ✅ | `003AB00000Abc12` (15-char) |
| `headshot_003AB00000Abc1DEFA.jpg` | ❌ | ID not at start |
| `001AB00000Abc1DEFA.jpg` | ❌ | Wrong prefix (Account) |
| `003AB00000Abc1DEFA.png` | ❌ | Unsupported extension |

---

## Setup Instructions

### Prerequisites

- **Python 3.9+**
- A Salesforce org with:
  - A Connected App configured for OAuth authentication
  - Contact records whose IDs match the filenames in your image folder

### Installation

```bash
# Navigate to the python directory
cd python

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install the package and dependencies (including dev/test dependencies)
pip install -e ".[dev]"
```

### Configure Credentials

#### Step 1 — Create a Connected App in Salesforce

1. Go to **Setup → App Manager → New Connected App**
2. Fill in the basic info:
   - **Connected App Name:** `Headshot Upload CLI`
   - **API Name:** `Headshot_Upload_CLI`
   - **Contact Email:** your email
3. Under **API (Enable OAuth Settings):**
   - Check **Enable OAuth Settings**
   - **Callback URL:** `https://login.salesforce.com/services/oauth2/callback`
   - **Selected OAuth Scopes:** Add at minimum:
     - `Manage user data via APIs (api)`
     - `Perform requests at any time (refresh_token, offline_access)`
   - Check **Enable Client Credentials Flow**
4. Click **Save**, then **Continue**
5. Wait 2–10 minutes for the Connected App to propagate

#### Step 2 — Configure the Client Credentials Flow Run-As User

1. Go to **Setup → App Manager** → find your Connected App → click **Manage**
2. Click **Edit Policies**
3. Under **Client Credentials Flow:**
   - Set **Run As** to the user the API calls should execute as
4. Click **Save**

#### Step 3 — Retrieve Consumer Key and Secret

1. Go to **Setup → App Manager** → find your Connected App → click **View**
2. Click **Manage Consumer Details** (you may need to verify via email/authenticator)
3. Copy the **Consumer Key** and **Consumer Secret**

#### Step 4 — Set Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and paste your credentials (see the [Authentication](#authentication) section below for details).

---

## Authentication

The tool supports two OAuth 2.0 flows. **Client Credentials is preferred** for server-to-server automation; **Username-Password** is available as a fallback.

The tool automatically detects which flow to use based on the environment variables you provide. If both are configured, Client Credentials takes priority.

### Option A — Client Credentials Flow (preferred)

| Variable | Required | Description |
|---|---|---|
| `SF_CLIENT_ID` | Yes | Connected App Consumer Key |
| `SF_CLIENT_SECRET` | Yes | Connected App Consumer Secret |

```dotenv
SF_CLIENT_ID=your_consumer_key
SF_CLIENT_SECRET=your_consumer_secret
```

### Option B — Username-Password Flow (fallback)

| Variable | Required | Description |
|---|---|---|
| `SF_CLIENT_ID` | Yes | Connected App Consumer Key |
| `SF_CLIENT_SECRET` | Yes | Connected App Consumer Secret |
| `SF_USERNAME` | Yes | Salesforce username |
| `SF_PASSWORD` | Yes | Salesforce password |
| `SF_SECURITY_TOKEN` | No | Security token (appended to password automatically) |

```dotenv
SF_CLIENT_ID=your_consumer_key
SF_CLIENT_SECRET=your_consumer_secret
SF_USERNAME=your_username
SF_PASSWORD=your_password
SF_SECURITY_TOKEN=your_security_token
```

### Optional Overrides

| Variable | Default | Description |
|---|---|---|
| `SF_LOGIN_URL` | `https://login.salesforce.com` | Override the login endpoint (e.g., My Domain URL) |
| `SF_API_VERSION` | `65.0` | Salesforce REST API version |

---

## Usage Examples

```bash
# Basic upload
headshot-upload --folder /path/to/headshots

# Upload to a sandbox org
headshot-upload --folder /path/to/headshots --environment sandbox

# Dry run — preview without uploading
headshot-upload --folder /path/to/headshots --dry-run

# Limit to first 10 files
headshot-upload --folder /path/to/headshots --limit 10

# Verbose output (DEBUG-level logging)
headshot-upload --folder /path/to/headshots --verbose

# Combined options
headshot-upload --folder ./headshots --environment sandbox --limit 5 --verbose

# Run as a Python module
python -m headshot_upload --folder /path/to/headshots --dry-run
```

---

## CLI Options

| Option | Type | Default | Description |
|---|---|---|---|
| `--folder` | Path (required) | — | Path to the folder containing headshot images |
| `--environment` | `prod` \| `sandbox` | `prod` | Target Salesforce environment |
| `--dry-run` | Flag | `false` | Preview planned actions without making API calls |
| `--limit` | Integer | All files | Maximum number of headshots to process |
| `--verbose` | Flag | `false` | Enable DEBUG-level logging output |
| `--version` | Flag | — | Display version and exit |
| `--help` | Flag | — | Display help text and exit |

---

## Running Tests

```bash
# Activate virtual environment
source venv/bin/activate

# Run all tests with coverage
pytest --cov=headshot_upload --cov-report=term-missing

# Run a specific test file
pytest tests/test_scanner.py -v

# Run tests matching a keyword
pytest -k "test_dry_run" -v
```

---

## Test Coverage Details

The project has **76 test cases** across 8 test files with **91% code coverage**. All tests use mocking — no real Salesforce API calls are made during testing.

| Test File | Module Under Test | Tests | What Is Tested |
|---|---|---|---|
| `test_config.py` | `config.py` | 9 | Environment variable loading, `is_client_credentials` / `is_username_password` property detection, sandbox URL, custom login URL, API version defaults, missing credentials validation |
| `test_auth.py` | `auth.py` | 9 | Client Credentials success, invalid client credentials, Username-Password success, security token concatenation, invalid UP credentials, no-credentials error, UP without client creds error, network errors, malformed response handling |
| `test_scanner.py` | `scanner.py` | 14 | Folder scanning with valid JPEGs, 15/18-char Contact ID extraction, sorted results, file attribute population, filtering of unsupported formats (PNG/GIF/TXT), invalid Contact ID skipping, empty folder, non-existent folder error, not-a-directory error, regex edge cases (wrong prefix, too short, special characters, empty string) |
| `test_encoder.py` | `encoder.py` | 5 | Valid base64 encoding with round-trip verification, UTF-8 string output, empty file encoding, file-not-found error, directory path error |
| `test_salesforce_api.py` | `salesforce_api.py` | 11 | Composite API ContentVersion creation (success, partial failure, HTTP error), empty list short-circuit, ContentDocumentId SOQL query, ContentDocumentLink creation (success, failure), empty list handling, retry on 500 then success, exhausted retries failure |
| `test_uploader.py` | `uploader.py` | 10 | End-to-end upload success (encode → CV → query → CDL), encoding failure handling, CV creation failure, CDL creation failure, empty list report, progress callback invocation, dry-run report format, dry-run empty list, UploadReport success rate calculation, zero-total division safety |
| `test_commands.py` | `commands.py` | 7 | Missing `--folder` option, invalid folder path, `--version` flag, dry-run preview display, dry-run with `--limit`, empty folder warning, successful upload results display |
| `conftest.py` | — | — | Shared fixtures: temporary folders with valid/invalid files, sample Contact IDs, minimal JPEG bytes, mock `SalesforceConfig`, mock `SalesforceSession` |

---

## Project Structure

```
python/
├── pyproject.toml                          ← Project config, dependencies, CLI entry point
├── requirements.txt                        ← Flat dependency list
├── .env.example                            ← Template for environment variables
├── .gitignore                              ← Git ignore rules
├── README.md                               ← This file
├── TALK_SCRIPT.md                          ← Video walkthrough script
├── headshot_upload/
│   ├── __init__.py                         ← Package metadata (__version__, __author__)
│   ├── __main__.py                         ← python -m headshot_upload entry point
│   ├── config.py                           ← Configuration loading, constants, validation
│   ├── cli/
│   │   ├── __init__.py
│   │   └── commands.py                     ← Click CLI — argument parsing, output formatting
│   └── modules/
│       ├── __init__.py
│       ├── auth.py                         ← OAuth 2.0 authentication (CC + UP flows)
│       ├── scanner.py                      ← Folder scanning, Contact ID extraction
│       ├── encoder.py                      ← Base64 file encoding
│       ├── salesforce_api.py               ← Composite API, retry logic, error parsing
│       └── uploader.py                     ← Business logic orchestration
├── tests/
│   ├── __init__.py
│   ├── conftest.py                         ← Shared fixtures (tmp folders, mock configs)
│   ├── test_config.py                      ← Configuration and auth-method detection tests
│   ├── test_auth.py                        ← OAuth flow tests (CC + UP)
│   ├── test_scanner.py                     ← Scanner and Contact ID extraction tests
│   ├── test_encoder.py                     ← Base64 encoding tests
│   ├── test_salesforce_api.py              ← Composite API and retry tests
│   ├── test_uploader.py                    ← Upload orchestration tests
│   └── test_commands.py                    ← CLI integration tests
├── images/                                 ← Sample headshot images for demo
└── logs/                                   ← Runtime log files (git-ignored)
```

---

## Design Decisions

| Decision | Rationale |
|---|---|
| **Composite API** over individual REST calls | Reduces API calls — batches up to 25 sub-requests per call |
| **`allOrNone: false`** on Composite requests | Enables partial success — one failure doesn't block the entire batch |
| **Separate CV + CDL creation** (not `FirstPublishLocationId`) | Explicit control over each step, clearer error tracking per record |
| **CV batch size of 10** (not 25) | Accounts for large base64 image payloads in the request body |
| **Retry with exponential back-off** | Handles transient 429/5xx errors gracefully (1s → 2s → 4s) |
| **`requests` library** (not `simple_salesforce`) | Full control over API calls, demonstrates raw REST API understanding |
| **No Click in modules** | Modules are reusable outside the CLI context |
| **No print in modules** | Modules use `logging` — output format is the CLI's responsibility |
| **`@dataclass` for data structures** | Auto-generates `__init__`, `__repr__`, `__eq__` — reduces boilerplate |
| **`python-dotenv` for local dev** | `.env` file loaded at CLI startup; production can use real env vars |

---

## Logging

The tool writes structured logs to both the console and a timestamped file in the `logs/` directory:

```
logs/headshot_upload_2026-02-28_153732.log
```

- **Console:** Shows `INFO` level by default, `DEBUG` with `--verbose`
- **File:** Always captures `DEBUG`-level detail for troubleshooting
- **Format:** `2026-02-28 15:37:32  INFO      module_name — message`
