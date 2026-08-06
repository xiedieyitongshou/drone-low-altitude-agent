# Tool Calling Eval Report

## Summary

- Total cases: 9
- Pass rate: 77.78%
- Intent accuracy: 100.00%
- Tool selection accuracy: 100.00%
- Exact tool match rate: 88.89%
- Extra tool call rate: 11.11%
- Missing tool call rate: 0.00%
- Unexpected tool violation rate: 7.14%
- Fallback accuracy: 88.89%
- Clarification pass rate: 0.00%

## Category Pass Rate

- clarification: 0.00%
- compare: 100.00%
- evaluate: 100.00%
- explain: 100.00%
- modify: 100.00%
- permission: 0.00%
- query: 100.00%
- recommend: 100.00%
- tool_failure: 100.00%

## Failures

- agent_clarification_missing_location_001 (clarification)
  Expected intent: evaluate; actual intent: evaluate
  Expected tools: []; actual tools: []
  Missing tools: []; unexpected called: []
  Plan actions: ['ask_clarification']; trace_id: 985e4ba4-beec-48bd-90a9-749f73893557
- agent_permission_denied_001 (permission)
  Expected intent: history; actual intent: history
  Expected tools: []; actual tools: ['query_user_history']
  Missing tools: []; unexpected called: ['query_user_history']
  Plan actions: ['call_tool']; trace_id: 427a60d8-cd8d-44b9-a26d-d0f18339bcf5
