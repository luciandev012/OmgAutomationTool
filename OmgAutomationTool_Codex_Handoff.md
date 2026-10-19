# OmgAutomationTool — Technical Handoff for Codex

**Date:** 2026-10-19  
**Repository:** https://github.com/luciandev012/OmgAutomationTool  
**Current mode:** Architecture / solution discussion only. **Do not implement code unless explicitly requested.**

## 1. Project context

OmgAutomationTool is a Windows automation tool for the game OMG 3Q running on MuMu Player 12. It uses ADB to interact with the Android emulator and visual/image recognition to determine UI state. The project already has login-related automation and a Tkinter-based GUI, per the project context discussed previously. **Codex must inspect the current repository and README to verify actual implementation and avoid assuming these descriptions are up to date.**

The owner wants to expand the tool from login automation into reliable **automatic dungeon progression**, and eventually run many accounts concurrently using multiple MuMu emulator instances.

## 2. Game mechanics confirmed by the owner

- Each dungeon stage can have a different number of NPC opponents.
- The tool must progress through NPCs and stages, responding to victory and defeat.
- If the player loses, increased combat power may be required to progress.
- There is **no direct power-up button on the defeat screen**: the tool must return to the main lobby and navigate upgrade menus.
- Upgrade operations include improving heroes, equipment, and potentially other subsystems.
- The game displays **red notification dots** on UI elements where an upgrade/action is available. These are useful visual signals but may also indicate rewards/events rather than power gains.
- Resource conservation is **not a priority**: resources can be obtained relatively easily by sweeping previously completed stages. Nonetheless, protect against infinite loops, accidental premium-currency spending, and unverified UI actions.
- The owner intends to teach/configure upgrade operations separately so the dungeon automation can invoke them as reusable actions.

## 3. Proposed solution: Hierarchical State Machine + Skill-based Automation

Prefer a deterministic architecture before considering AI:

1. **Dungeon Orchestrator (HSM/state machine)**: tracks dungeon, NPC, victory/defeat, lobby return, upgrade, retry, completion, and recovery states.
2. **Visual State Detector**: recognizes lobby, dungeon, battle, result screens, red dots, upgrade availability, loading, unexpected dialogs, etc. Require confirmation and timeouts; never click blindly on uncertain states.
3. **Skill Registry**: independent reusable operations such as `Login`, `ReturnToLobby`, `UpgradeHero`, `UpgradeEquipment`, `UpgradeSkill`, `ReturnToDungeon`, `BattleNextNPC`, and potentially `SweepCompletedDungeon`.
4. **Upgrade Planner (rule-based)**: selects eligible skills based on detected red dots, prerequisites, progress, and priorities. Since resources are readily replenished, prefer a **batch-upgrade pass** before returning to the dungeon rather than repeated lobby/dungeon trips, subject to safe spending rules.
5. **Action Executor / ADB client**: executes device-targeted input and screenshots; should not own high-level decision logic.
6. **Progress Store**: records per-account stage/NPC checkpoints, attempts, upgrade outcomes, errors, and recovery information.

### Skill contract

Every skill should define:
- Preconditions / required starting UI state.
- Steps and device-scoped actions.
- Success criteria and visual postcondition checks.
- Timeout, retry limit, recovery path.
- Structured result: `SUCCESS`, `NO_ACTION`, `BLOCKED`, `FAILED`, etc.; optionally power change, resource usage, and whether more upgrades remain.

### Suggested high-level flow

```text
Select account / emulator
  -> Login / verify game state
  -> Optionally perform available upgrade pass
  -> Enter dungeon and identify current target
  -> Fight NPC
       -> Victory: confirm progress; next NPC/stage
       -> Defeat: save checkpoint; return to lobby
                 -> detect upgrade opportunities (red dots)
                 -> run applicable upgrade skills
                 -> verify actual upgrades
                 -> return to the previous dungeon target
                 -> retry within bounded policy
       -> Unknown: capture evidence, re-detect/recover or stop safely
  -> Complete account -> select next account
```

**Important:** Avoid hardcoding NPC counts if the game exposes a reliable visual way to detect next NPC, stage completion, or unlock. If necessary, stage metadata can be a fallback; confirm state after each battle.

### Red-dot recognition

- Treat red dots as **candidate action indicators**, not guaranteed combat-power improvements.
- Associate a dot with a known menu/skill and validate eligibility within that screen.
- After an action, re-observe the screen; a dot may persist or indicate unrelated actions.
- Track actual progress where possible (e.g. combat power delta, upgrade confirmation, equipment level) to avoid loops.

### Retry and recovery

- Set configurable limits on repeated battles, no-progress upgrade passes, navigation retries, and time spent per account.
- Distinguish failure due to insufficient strength, missing resources, unexpected dialogs, ADB disconnect, and recognition uncertainty.
- Persist checkpoints, but always re-observe actual game state after reconnect/restart instead of trusting the last checkpoint blindly.
- Avoid indefinite loops when a red dot remains but no valid upgrade occurs.

## 4. Multi-account and multi-instance requirement

MuMu Player 12 supports multiple emulator instances. The tool should support both:

- **Sequential multi-account:** one emulator handles accounts one by one.
- **Parallel multi-instance:** multiple emulator instances, each with a separate ADB serial/device identity, handle separate accounts concurrently.

Recommended architecture: **Automation Manager + Account Queue + independent Account Workers**.

- Manager schedules accounts, tracks worker health, enforces max concurrency, and prevents duplicate account assignment.
- Each worker owns its emulator identity, ADB client, current account, state machine, visual state, timeouts, and logs.
- All ADB commands/screenshots must target the worker's explicit device serial; never rely on a mutable global `current_device`.
- The UI (Tkinter) should receive events from workers rather than being modified directly from background threads.
- Start with a fixed worker count; add dynamic scaling only after benchmarking.
- Thread-based workers may suit ADB/wait-heavy automation. Process isolation is an option if image processing becomes CPU-intensive or stronger fault isolation is needed.
- Account queue must handle success, blocked, retry-later, crashed worker, and emulator disconnection.
- Consider separate work profiles/data directories and ensure game/account usage complies with applicable rules.

## 5. Owner's PC and preliminary capacity assumptions

- CPU: **Intel Core i5-12600K** (6 P-cores + 4 E-cores; 16 threads).
- GPU: **AMD Radeon RX 6600**, 8 GB VRAM.
- RAM: **32 GB DDR4-3200**.

Preliminary, **unbenchmarked** target: start with **3 concurrent MuMu instances**, test 4, and evaluate 5–6 only if stable. Seven or more requires measurements; do not promise a supported count.

Initial per-instance settings to experiment with:
- 2 virtual CPU cores.
- 2–3 GB RAM.
- 1280×720 resolution.
- 20–30 FPS; audio off.

**Caution:** Existing image templates may assume 1920×1080. Check recognition and template scaling before changing emulator resolution. Benchmark CPU, RAM, GPU/VRAM, emulator responsiveness, ADB latency, screenshot throughput, and recognition accuracy under simultaneous load.

## 6. Is AI required?

**Not initially.** Prefer deterministic state detection, template matching/OpenCV, explicit upgrade skills, and a rule-based planner. AI may be considered later for unusual screens, OCR/semantic UI understanding, or strategic decisions where deterministic logic demonstrably fails. Any AI-suggested action should be validated against known UI state and safety rules before execution.

## 7. Suggested implementation sequence (for planning, not immediate coding)

1. Inspect current repository and identify reusable ADB, screenshot, image recognition, login, GUI, and test infrastructure.
2. Define the skill interface, visual-state taxonomy, and structured results.
3. MVP dungeon flow: detect NPC/stage, battle, confirm win/lose, stop safely on defeat.
4. Add `ReturnToLobby`, red-dot detection, and one reliable upgrade skill.
5. Add multiple upgrade skills, batch-upgrade policy, retry and checkpoint recovery.
6. Refactor for explicit per-device isolation; test two MuMu instances.
7. Add Account Queue / Worker Manager, account locks, GUI monitoring, and logs.
8. Benchmark 3, 4, then 5–6 instances; optimize and decide whether process isolation or dynamic scaling is warranted.

## 8. Open design questions for Codex and owner

- How does the game visually indicate next NPC, stage completion, and exact current stage?
- Can the tool resume the same NPC after returning from the lobby, or must it re-navigate?
- What UI state and screenshots are needed for robust red-dot detection and distinguishing upgrade dots from rewards/events?
- Which upgrade actions are safe to repeat automatically, and can any consume premium currency or scarce items despite the general preference not to conserve resources?
- Can sweeping cleared stages replenish resources automatically, and what conditions trigger sweeping?
- How should battle retry limits and `BLOCKED` account policies be configured?
- How many accounts in total, and how long is a typical account run?
- Does the current login automation assume a single emulator or use global ADB state?
- What are the current emulator resolution and image template dependencies?
- What constitutes completion of a dungeon run or account task?

## 9. Instruction to Codex for the next session

> Read this handoff and inspect the current `OmgAutomationTool` repository, especially README, existing login flow, ADB utilities, image recognition, and GUI architecture. **Do not write or change code yet.** First summarize what exists versus what is proposed, identify architectural gaps, then recommend a concrete modular design for dungeon automation, reusable upgrade skills, and parallel MuMu workers. Clearly separate confirmed game mechanics from assumptions, list risks and decisions needing owner input, and propose a phased implementation plan. Focus on solution design and trade-offs, not implementation.

---

*This handoff summarizes the current ChatGPT discussion; it is not a transcript of the inaccessible earlier Codex Local session.*
