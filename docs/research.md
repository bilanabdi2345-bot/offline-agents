# Research behind this project

Papers and code that use the same ideas.

## IsolateGPT (also called SecGPT), NDSS 2025

The closest match. Each app runs in its own sandbox (a "spoke").
Spokes only talk through a trusted hub. Our coordinator is the hub.

- Paper: https://arxiv.org/abs/2403.04960
- Code: https://github.com/llm-platform-security/SecGPT

## CaMeL: Defeating Prompt Injections by Design, Google DeepMind and ETH Zürich, 2025

A protective layer around the model, so untrusted data cannot change what the system does.
Useful ideas for making the coordinator's rules stronger.

- Paper: https://arxiv.org/abs/2503.18813
- Code: https://github.com/google-research/camel-prompt-injection

## Agent Privilege Separation in OpenClaw, 2026

Splits one agent into two, each with different tools.

- Paper: https://arxiv.org/abs/2603.13424

## Sandlock, 2026

A lighter and faster way to sandbox agents than Docker.

- Paper: https://arxiv.org/abs/2605.26298
- Code: https://github.com/multikernel/sandlock
