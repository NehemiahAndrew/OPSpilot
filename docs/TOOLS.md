# Tools Reference

Every tool in OpsPilot returns a `ToolResult` and receives a `ToolContext`. This document catalogs every tool exposed to agents.

---

## Tool Result Contract

```python
class ToolResult(BaseModel):
    success: bool
    data: Optional[Any]
    error: Optional[str]
    tool_call_id: str          # UUID generated per call
    tool_name: str
    retrieved_at: datetime
    source: Literal["database"]  # never "model_knowledge"
    duration_ms: int
    arguments: dict
```

## Tool Context

```python
class ToolContext(BaseModel):
    business_id: str
    requesting_user_id: str
    user_role: Literal["manager", "admin"]
    run_id: str
    step_id: str
```

---

## Read Tools

### `get_employee`

| | |
|---|---|
| **Purpose** | Look up an employee by name, ID, or emp_code |
| **Risk** | `read` |
| **Signature** | `async def get_employee(identifier: str, ctx: ToolContext) -> ToolResult` |

**Input Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `identifier` | string | yes | Employee name, UUID, or emp_code (e.g. "EMP-001") |

**Output Schema (on success):**

```json
{
  "employee_id": "uuid",
  "emp_code": "EMP-001",
  "first_name": "Sarah",
  "last_name": "Mitchell",
  "name": "Sarah Mitchell",
  "email": "sarah@acme.com",
  "role": "Store Manager",
  "department_id": "uuid",
  "manager_id": "uuid",
  "status": "active",
  "employment_type": "full-time",
  "hire_date": "2022-03-15"
}
```

**Error Cases:**

| Error | Meaning |
|---|---|
| `EMPLOYEE_NOT_FOUND` | No employee matches the identifier |
| `AMBIGUOUS_EMPLOYEE` | Multiple employees match; `data` contains list of matches |

**Example:**

```python
r = await get_employee("EMP-001", ctx)
# r.success = True, r.data["name"] = "Sarah Mitchell"

r = await get_employee("John", ctx)
# r.success = False, r.error = "AMBIGUOUS_EMPLOYEE"
# r.data = [{...}, {...}]  # list of matching employees
```

---

### `get_employee_by_id`

| | |
|---|---|
| **Purpose** | Look up an employee by UUID or emp_code |
| **Risk** | `read` |
| **Signature** | `async def get_employee_by_id(employee_id: str, ctx: ToolContext) -> ToolResult` |

**Input Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `employee_id` | string | yes | Employee UUID or emp_code |

**Error Cases:**

| Error | Meaning |
|---|---|
| `EMPLOYEE_NOT_FOUND` | No employee matches |

---

### `get_leave_balance`

| | |
|---|---|
| **Purpose** | Get an employee's leave balance for a given year |
| **Risk** | `read` |
| **Signature** | `async def get_leave_balance(employee_id: str, as_of_date: date, ctx: ToolContext) -> ToolResult` |

**Input Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `employee_id` | string | yes | Employee UUID or emp_code |
| `as_of_date` | date | yes | Date to check balance for (year is extracted) |

**Output Schema:**

```json
{
  "leave_balance_id": "uuid",
  "employee_id": "uuid",
  "employee_name": "Sarah Mitchell",
  "emp_code": "EMP-001",
  "leave_type": "annual",
  "annual_entitlement": 20.0,
  "used_days": 12.0,
  "remaining_days": 8.0,
  "available_days": 8.0,
  "year": 2026
}
```

**Error Cases:**

| Error | Meaning |
|---|---|
| `LEAVE_BALANCE_NOT_FOUND` | No leave balance record found for employee |

---

### `get_policy`

| | |
|---|---|
| **Purpose** | Get policies by category. Department-specific policies override company-wide ones. |
| **Risk** | `read` |
| **Signature** | `async def get_policy(category: str, ctx: ToolContext, department_id: Optional[str] = None) -> ToolResult` |

**Input Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `category` | string | yes | Policy category (e.g. "annual_leave_policy") |
| `department_id` | string | no | Filter by department |

**Output Schema (on success):**

```json
[
  {
    "policy_id": "uuid",
    "policy_code": "POL-001",
    "title": "Annual Leave Policy",
    "category": "annual_leave_policy",
    "version": 3,
    "is_active": true,
    "rules": { ... },
    "department_id": null,
    "risk_level": "low",
    "effective_from": "2026-01-01",
    "effective_until": null,
    "approval_requirements": { ... }
  }
]
```

**Notes:** Department-specific policies are returned first, overriding company-wide policies where they conflict.

**Error Cases:**

| Error | Meaning |
|---|---|
| `POLICY_NOT_FOUND` | No active policies match the category |

---

### `get_schedule`

| | |
|---|---|
| **Purpose** | Get an employee's schedule for a date range |
| **Risk** | `read` |
| **Signature** | `async def get_schedule(employee_id: str, date_range_start: date, date_range_end: date, ctx: ToolContext) -> ToolResult` |

**Input Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `employee_id` | string | yes | Employee UUID or emp_code |
| `date_range_start` | date | yes | Start of date range |
| `date_range_end` | date | yes | End of date range (inclusive) |

**Output Schema:**

```json
[
  {
    "schedule_id": "uuid",
    "employee_id": "uuid",
    "emp_code": "EMP-001",
    "employee_name": "Sarah Mitchell",
    "date": "2026-09-04",
    "shift_start": "09:00",
    "shift_end": "17:00",
    "shift_type": "regular",
    "status": "WORKING"
  }
]
```

**Notes:** Returns an empty list if no shifts are scheduled.

---

### `get_team_coverage`

| | |
|---|---|
| **Purpose** | Calculate team coverage for a department on a given date |
| **Risk** | `read` |
| **Signature** | `async def get_team_coverage(department_id: str, target_date: date, ctx: ToolContext) -> ToolResult` |

**Input Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `department_id` | string | yes | Department UUID |
| `target_date` | date | yes | Date to check coverage for |

**Output Schema:**

```json
{
  "department_id": "uuid",
  "department_name": "Operations",
  "target_date": "2026-09-04",
  "employees_available": 4,
  "minimum_required": 3,
  "is_coverage_sufficient": true,
  "available_employees": [
    { "employee_id": "uuid", "name": "Sarah Mitchell", "emp_code": "EMP-001" }
  ],
  "unavailable_employees": []
}
```

**Error Cases:**

| Error | Meaning |
|---|---|
| `DEPARTMENT_NOT_FOUND` | Department does not exist |

---

### `get_pending_requests`

| | |
|---|---|
| **Purpose** | Get pending requests for an employee (duplicate detection) |
| **Risk** | `read` |
| **Signature** | `async def get_pending_requests(employee_id: str, ctx: ToolContext) -> ToolResult` |

**Input Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `employee_id` | string | yes | Employee UUID or emp_code |

**Output Schema:**

```json
[
  {
    "request_id": "uuid",
    "request_type": "leave",
    "status": "pending",
    "created_at": "2026-09-01T10:30:00Z",
    "structured_request": { "dates": ["2026-09-04"] }
  }
]
```

**Notes:** Returns requests with status `pending`, `processing`, or `awaiting_approval`. Returns empty list if none found.

---

### `get_task_assignments`

| | |
|---|---|
| **Purpose** | Get task assignments for an employee |
| **Risk** | `read` |
| **Signature** | `async def get_task_assignments(employee_id: str, ctx: ToolContext) -> ToolResult` |

**Input Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `employee_id` | string | yes | Employee UUID or emp_code |

**Output Schema:**

```json
[
  {
    "task_id": "uuid",
    "title": "API Gateway Migration",
    "description": "...",
    "assigned_to": "uuid",
    "employee_name": "David Chen",
    "priority": "high",
    "status": "in_progress",
    "due_date": "2026-09-15"
  }
]
```

---

### `get_attendance`

| | |
|---|---|
| **Purpose** | Get attendance records for an employee over the past N days |
| **Risk** | `read` |
| **Signature** | `async def get_attendance(employee_id: str, days_back: int, ctx: ToolContext) -> ToolResult` |

**Input Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `employee_id` | string | yes | Employee UUID or emp_code |
| `days_back` | integer | yes | Number of days to look back |

**Output Schema:**

```json
{
  "records": [
    {
      "attendance_id": "uuid",
      "employee_id": "uuid",
      "emp_code": "EMP-002",
      "employee_name": "John Carter",
      "date": "2026-08-15",
      "scheduled_start": "09:00",
      "actual_start": "09:25",
      "status": "late",
      "notes": null
    }
  ],
  "late_count": 4,
  "warning_count": 2,
  "total_records": 30
}
```

**Notes:** The `late_count` and `warning_count` are computed from the returned records.

---

### `get_historical_decisions`

| | |
|---|---|
| **Purpose** | Get historical decisions for an employee from agent_memory |
| **Risk** | `read` |
| **Signature** | `async def get_historical_decisions(employee_id: str, request_type: str, ctx: ToolContext, limit: int = 5) -> ToolResult` |

**Input Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `employee_id` | string | yes | Employee UUID or emp_code |
| `request_type` | string | yes | Type of request (e.g. "leave_request") |
| `limit` | integer | no | Max results (default 5) |

**Output Schema:**

```json
{
  "decisions": [
    {
      "decision_id": "uuid",
      "employee_id": "uuid",
      "emp_code": "EMP-001",
      "employee_name": "Sarah Mitchell",
      "request_type": "leave_request",
      "decision": "approved",
      "reason": "Coverage confirmed",
      "decided_by": "manager",
      "created_at": "2026-07-15T14:00:00Z"
    }
  ],
  "total_count": 2,
  "label": "HISTORICAL",
  "warning": "These are previous operational decisions, NOT current policy."
}
```

**Notes:** Results are labeled as `HISTORICAL` and should never be treated as current policy.

---

## Action Tools

Action tools write to the database. They require explicit authorization tier validation and are NEVER called directly by LLM agents. They are called only by the Action Executor after authorization has been confirmed.

### `create_leave_request`

| | |
|---|---|
| **Purpose** | Create a leave request (Tier 2 — reversible) |
| **Risk** | `reversible` |
| **Signature** | `async def create_leave_request(employee_id: str, dates: List[date], reason: str, policy_id: str, run_id: str, ctx: ToolContext) -> ToolResult` |

**Input Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `employee_id` | string | yes | Employee UUID |
| `dates` | list[date] | yes | Leave dates |
| `reason` | string | yes | Reason for leave |
| `policy_id` | string | yes | Applicable policy UUID |
| `run_id` | string | yes | Agent run UUID |

**Output Schema:**

```json
{
  "request_id": "uuid",
  "status": "pending"
}
```

**Notes:**
- **Idempotent:** Checks for duplicate before creating. Returns `DUPLICATE_REQUEST` if identical request exists.
- Records in `audit_logs`.

**Error Cases:**

| Error | Meaning |
|---|---|
| `DUPLICATE_REQUEST` | Identical request already exists (idempotency guard) |

---

### `create_approval_request`

| | |
|---|---|
| **Purpose** | Create a pending approval record (always allowed) |
| **Risk** | `reversible` |
| **Signature** | `async def create_approval_request(run_id: str, decision_id: str, approval_reason: str, authorization_tier: int, risk_level: str, ctx: ToolContext) -> ToolResult` |

**Input Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `run_id` | string | yes | Agent run UUID |
| `decision_id` | string | yes | Decision UUID |
| `approval_reason` | string | yes | Reason for approval request |
| `authorization_tier` | integer | yes | Tier (1, 2, or 3) |
| `risk_level` | string | yes | Risk level (low, medium, high, critical) |

**Output Schema:**

```json
{
  "approval_id": "uuid",
  "status": "pending"
}
```

**Notes:** This is how Tier 3 actions get queued for human approval.

---

### `update_request_status`

| | |
|---|---|
| **Purpose** | Update request status with legal transition validation |
| **Risk** | `consequential` |
| **Signature** | `async def update_request_status(request_id: str, new_status: str, ctx: ToolContext) -> ToolResult` |

**Input Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `request_id` | string | yes | Request UUID |
| `new_status` | string | yes | New status to set |

**Legal Transitions:**

| Current Status | Allowed Transitions |
|---|---|
| `pending` | `processing`, `awaiting_approval`, `rejected`, `completed` |
| `processing` | `awaiting_approval`, `approved`, `rejected`, `completed` |
| `awaiting_approval` | `approved`, `rejected` |
| `approved` | `completed` |
| `rejected` | (none) |
| `completed` | (none) |

**Error Cases:**

| Error | Meaning |
|---|---|
| `REQUEST_NOT_FOUND` | Request does not exist |
| `ILLEGAL_TRANSITION` | Status transition is not allowed; `data` contains current status and allowed transitions |

---

## Tool Registry

All tools are registered in the `ToolRegistry` which:

1. Validates tool names and schemas
2. Records every call in `agent_tool_calls` table
3. Filters tools by risk classification

```python
from backend.app.tools.registry import registry

# List all read tools
read_tools = registry.list_tools(risk_filter="read")

# Call a tool
result = await registry.call_tool("get_employee", {"identifier": "EMP-001"}, ctx)
```
