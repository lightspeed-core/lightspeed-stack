# End-to-end LCS log evidence (LCORE-2657 PoC)

```
2026-07-20 12:15:15.423 WARNING:  Prompt guardrails PoC ACTIVE: 5 rules, detector=http://localhost:11434/v1 model=granite3-guardian:2b  [lightspeed_stack.guardrails.poc_loader:39]
2026-07-20 12:15:29.844 INFO:     Guardrail rule 'jailbreak' at point 'input': flagged=False (14412 ms, raw='No')  [lightspeed_stack.guardrails.granite_guardian:145]
2026-07-20 12:15:29.844 INFO:     Guardrail rule 'leet-speak' at point 'input': flagged=False (7143 ms, raw='No')  [lightspeed_stack.guardrails.granite_guardian:145]
2026-07-20 12:15:56.180 INFO:     Guardrail rule 'harm-out' at point 'output': flagged=False (24201 ms, raw='No')  [lightspeed_stack.guardrails.granite_guardian:145]
2026-07-20 12:15:56.180 INFO:     Guardrail rule 'answer-relevance' at point 'output': flagged=False (15203 ms, raw='No')  [lightspeed_stack.guardrails.granite_guardian:145]
2026-07-20 12:15:58.750 WARNING:  Shield 'llama-guard' flagged content: categories={'Violent Crimes': False, 'Non-Violent Crimes': False, 'Sex Crimes': False, 'Child Exploitation': False, 'Defamation': False, 'Specialized Advice': True, 'Privacy': False, 'Intellectual Property': False, 'Indiscriminate Weapons': False, 'Hate': False, 'Self-Harm': False, 'Sexual Content': False, 'Elections': False, 'Code Interpreter Abuse': False}  [lightspeed_stack.utils.shields:184]
2026-07-20 12:16:01.177 WARNING:  Shield 'llama-guard' flagged content: categories={'Violent Crimes': False, 'Non-Violent Crimes': True, 'Sex Crimes': False, 'Child Exploitation': False, 'Defamation': False, 'Specialized Advice': True, 'Privacy': False, 'Intellectual Property': False, 'Indiscriminate Weapons': False, 'Hate': False, 'Self-Harm': False, 'Sexual Content': False, 'Elections': False, 'Code Interpreter Abuse': True}  [lightspeed_stack.utils.shields:184]
2026-07-20 12:17:15.127 INFO:     Guardrail rule 'jailbreak' at point 'input': flagged=True (15199 ms, raw='Yes')  [lightspeed_stack.guardrails.granite_guardian:145]
2026-07-20 12:17:15.128 INFO:     Guardrail rule 'leet-speak' at point 'input': flagged=True (8536 ms, raw='Yes')  [lightspeed_stack.guardrails.granite_guardian:145]
2026-07-20 12:17:32.904 INFO:     Guardrail rule 'jailbreak' at point 'input': flagged=True (16643 ms, raw='Yes')  [lightspeed_stack.guardrails.granite_guardian:145]
2026-07-20 12:17:32.904 INFO:     Guardrail rule 'leet-speak' at point 'input': flagged=True (9737 ms, raw='Yes')  [lightspeed_stack.guardrails.granite_guardian:145]
```
