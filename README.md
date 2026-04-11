# Entry-Centered Ledger Balance Tool
# 分录驱动配平系统

---

## Core Concept | 核心思想

This tool processes a general ledger by tracking the **remaining balance of each individual entry**, rather than grouping entries by project name.

系统以每条**分录的剩余金额**为核心，而非按项目归组处理。

- Every imported row tagged as `entry` receives an `original_amount` and a `remaining_amount`.
- The matching engine continuously reduces `remaining_amount` by creating match records.
- An entry with `remaining_amount == 0` is fully matched (已配平).
- An entry with `0 < remaining_amount < original_amount` is partially matched (部分匹配).
- An entry with `remaining_amount == original_amount` is unmatched (未匹配).

---

## System Architecture | 系统架构

```mermaid
flowchart TD
    A[Import Data\n导入数据] --> B[(entries\nremaining_amount)]

    B --> C{Matching Engine\n匹配引擎}

    C --> C1[Full Match\n全额匹配 1:1]
    C --> C2[Partial Match\n部分匹配 1:1]
    C --> C3[Combination Match\n组合匹配 1:N / N:1 ≤3]

    C1 & C2 & C3 --> D[(match_records\n匹配记录)]
    D --> E[(match_links\n配平明细)]
    E --> F[Update remaining_amount\n扣减剩余金额]
    F --> G{Any new match?\n是否还有可配对项?}
    G -- Yes --> C
    G -- No --> H[Done\n配平完成]

    B --> I[AI Suggestion\nAI 候选分析\nnon-persistent]
    I --> J[User Confirm\n用户确认]
    J --> D

    D --> K[Cancel Match\n取消匹配]
    K --> F
```

---

## Data Model | 数据模型

```mermaid
erDiagram
    entries {
        int id
        string summary
        decimal debit_amount
        decimal credit_amount
        string amount_side
        decimal original_amount
        decimal remaining_amount
        string row_type
    }

    match_records {
        int id
        string match_type
        string match_mode
        decimal matched_amount
        string reason
    }

    match_links {
        int id
        int match_record_id
        int entry_id
        decimal used_amount
    }

    match_records ||--o{ match_links : "has"
    entries ||--o{ match_links : "referenced by"
```

---

## Matching Logic | 匹配逻辑

The engine runs the following strategies in order, repeating until no new match is created:

1. **Full Match (1:1 exact)** — debit `remaining_amount` equals credit `remaining_amount` exactly.
2. **Partial Match (1:1 min)** — match up to the smaller of the two remaining amounts.
3. **Combination Match (1:N / N:1, up to 3 entries)** — find a group of entries on one side whose `remaining_amount` values sum to the other side's amount.
4. **Run in cycle** — steps 1–3 repeat in a loop until no new match record is created.

Matching is triggered either automatically (`run_matching_cycle`) or manually (user selects entries and confirms).

---

## UI Workflow | 界面操作流程

```mermaid
flowchart LR
    subgraph Left["Left Panel | 左栏"]
        L1[entries\nremaining_amount > 0]
    end

    subgraph Middle["Middle Panel | 中栏"]
        M1[Auto Match\n自动匹配]
        M2[AI Suggestions\nAI 候选建议]
    end

    subgraph Right["Right Panel | 右栏"]
        R1[Match Records\n已匹配记录]
        R2[Confirm Match\n确认匹配]
        R3[Cancel Match\n取消匹配]
    end

    L1 --> M1
    L1 --> M2
    M1 --> R1
    M2 --> R2
    R2 --> R1
    R1 --> R3
    R3 --> L1
```

---

## AI Behavior | AI 行为约束

- AI **only provides suggestions** based on entry summaries and amounts. AI 仅提供候选建议。
- AI **does NOT write to the database**. AI 不直接写入数据库。
- A match record is created **only after explicit user confirmation**. 只有用户确认后才会创建匹配记录。

---

## Project Structure | 项目结构

```
src/ledger/
├── services/
│   ├── importer.py          # CSV / Excel import, row_type detection
│   ├── matching_engine.py   # Full / partial / combination matching
│   ├── ai_suggester.py      # AI candidate analysis (read-only)
│   ├── balance_trace.py     # Trace display helpers
│   ├── attribution.py       # Text normalization, correction rules
│   └── exporter.py          # Excel export
├── storage/
│   ├── db.py                # SQLite schema, migration guard
│   └── repository.py        # Data access layer
└── ui/
    ├── main_window.py
    ├── import_page.py
    ├── results_page.py
    └── settings_page.py
```

---

