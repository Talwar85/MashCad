# MashCAD V1 Production Readiness Plan

**Executive Entrypoint**  
**Version:** 1.0.0  
**Status:** Canonical  
**Last Updated:** 2026-02-22

---

## Executive Summary

This document serves as the executive entrypoint for MashCAD V1 production readiness planning. It provides a high-level overview and links to the comprehensive documentation set.

**V1 Goal:** Deliver a production-ready CAD application that enables users to reliably create, modify, and export parametric 3D models for 3D printing.

---

## Quick Navigation

| Document | Purpose |
|----------|---------|
| [**Master Index**](roadmap_ctp/v1/00_INDEX.md) | Full documentation navigation |
| [**V1 Charter**](roadmap_ctp/v1/01_V1_CHARTER_AND_NON_NEGOTIABLES.md) | Non-negotiable product criteria |
| [**Gate Matrix**](roadmap_ctp/v1/06_GATE_MATRIX_G0_G7.md) | Release gates and criteria |
| [**Workstream Order**](roadmap_ctp/v1/08_WORKSTREAM_PRIORITY_AND_DEPENDENCY_ORDER.md) | Execution sequence |

---

## Current Status

### Gate Progress

| Gate | Name | Status |
|------|------|--------|
| G0 | Baseline & Scope Lock | ⬜ Not Started |
| G1 | Core Stability Recovery | ⬜ Not Started |
| G2 | Parametric Integrity | ⬜ Not Started |
| G3 | Sketcher & UX Reliability | ⬜ Not Started |
| G4 | Printability & Export Trust | ⬜ Not Started |
| G5 | Assembly V1 Readiness | ⬜ Not Started |
| G6 | RC Burn-in | ⬜ Not Started |
| G7 | V1 GA Go/No-Go | ⬜ Not Started |

### Key Metrics (Baseline)

| Metric | Current | Target |
|--------|---------|--------|
| Test pass rate | ~75% | 100% |
| P0 bugs | TBD | 0 |
| `except: pass` in core | 28 | 0 |
| TNP reliability | TBD | 100% |

---

## Non-Negotiable Invariants

V1 will not be released until these invariants are satisfied:

### 1. CAD Kernel Compliance
All geometry code follows OCP-first patterns with proper validation.
→ See: [CAD Kernel Compliance Policy](roadmap_ctp/v1/02_CAD_KERNEL_COMPLIANCE_POLICY.md)

### 2. Zero Fallbacks
No silent failures, no `except: pass`, no degradation patterns.
→ See: [Zero Fallback Policy](roadmap_ctp/v1/03_ZERO_FALLBACK_POLICY.md)

### 3. Anti-Monolith Architecture
File size limits enforced, module boundaries respected.
→ See: [Anti-Monolith Constraints](roadmap_ctp/v1/04_ANTI_MONOLITH_ARCHITECTURE_CONSTRAINTS.md)

### 4. TNP 100% Reliability
Topology references must resolve 100% in test corpus.
→ See: [TNP 100% Reliability Program](roadmap_ctp/v1/05_TNP_100_RELIABILITY_PROGRAM.md)

---

## Timeline Overview

```
Phase 1: Foundation (G0 → G1)           Weeks 1-3
Phase 2: Parametric Core (G1 → G2)      Weeks 4-6
Phase 3: User Experience (G2 → G3)      Weeks 7-9
Phase 4: Export Trust (G3 → G4)         Weeks 10-11
Phase 5: Assembly (G4 → G5)             Weeks 12-13
Phase 6: Performance & Polish (G5 → G6) Weeks 14-16
Phase 7: Release (G6 → G7)              Week 17+

Target: V1.0.0 GA after Gate G7 passed
```

---

## Workstream Summary

| Priority | Workstream | Gate Target |
|----------|------------|-------------|
| 1 | Core Stability and Failure Hardening | G1 |
| 2 | Parametric Integrity (TNP + History) | G2 |
| 3 | Sketcher Reliability and Interaction | G3 |
| 4 | UX Discoverability and Accessibility | G3 |
| 5 | 3D Print Readiness and Export Trust | G4 |
| 6 | Assembly Usability | G5 |
| 7 | Architecture Refactoring | Ongoing |
| 8 | Test Strategy and CI Enforcement | Ongoing |
| 9 | Performance under Load | G6 |
| 10 | Product Readiness (Docs) | G6/G7 |

→ See: [Workstream Priority and Dependency Order](roadmap_ctp/v1/08_WORKSTREAM_PRIORITY_AND_DEPENDENCY_ORDER.md)

---

## Key Policies

### Priority Rule (Binding)

When in conflict, this order is final:

1. **Data Integrity** - Geometry must never be corrupted
2. **Rebuild/Solver Stability** - Parametrics must work reliably
3. **Operation Consistency** - UX must be predictable
4. **Performance Under Load** - Must remain responsive
5. **New Features** - Only after above are satisfied

### No-Go Conditions

V1 release is automatically blocked if:
- Any gate G0-G6 not passed
- Any P0/P1 defect open
- Core journey regression
- Data integrity risk open

---

## Documentation Set

### Planning Documents

| Document | Description |
|----------|-------------|
| [00_INDEX.md](roadmap_ctp/v1/00_INDEX.md) | Master index and navigation |
| [01_V1_CHARTER_AND_NON_NEGOTIABLES.md](roadmap_ctp/v1/01_V1_CHARTER_AND_NON_NEGOTIABLES.md) | V1 definition and non-negotiables |
| [06_GATE_MATRIX_G0_G7.md](roadmap_ctp/v1/06_GATE_MATRIX_G0_G7.md) | Gate definitions and criteria |
| [08_WORKSTREAM_PRIORITY_AND_DEPENDENCY_ORDER.md](roadmap_ctp/v1/08_WORKSTREAM_PRIORITY_AND_DEPENDENCY_ORDER.md) | Execution sequence |
| [09_ROLLOUT_ROLLBACK_AND_RISK_MODEL.md](roadmap_ctp/v1/09_ROLLOUT_ROLLBACK_AND_RISK_MODEL.md) | Release and risk management |
| [10_DOC_REWRITE_DEFINITION_OF_DONE.md](roadmap_ctp/v1/10_DOC_REWRITE_DEFINITION_OF_DONE.md) | Documentation standards |

### Technical Policy Documents

| Document | Description |
|----------|-------------|
| [02_CAD_KERNEL_COMPLIANCE_POLICY.md](roadmap_ctp/v1/02_CAD_KERNEL_COMPLIANCE_POLICY.md) | OCP-first standards |
| [03_ZERO_FALLBACK_POLICY.md](roadmap_ctp/v1/03_ZERO_FALLBACK_POLICY.md) | Error handling requirements |
| [04_ANTI_MONOLITH_ARCHITECTURE_CONSTRAINTS.md](roadmap_ctp/v1/04_ANTI_MONOLITH_ARCHITECTURE_CONSTRAINTS.md) | Module boundary rules |
| [05_TNP_100_RELIABILITY_PROGRAM.md](roadmap_ctp/v1/05_TNP_100_RELIABILITY_PROGRAM.md) | Topology naming reliability |
| [07_CI_CD_GATE_ENFORCEMENT_MAPPING.md](roadmap_ctp/v1/07_CI_CD_GATE_ENFORCEMENT_MAPPING.md) | CI/CD integration |

### Historical Reference

| Document | Status |
|----------|--------|
| [roadmap_ctp/origin/](roadmap_ctp/origin/) | Historical baseline (superseded) |

---

## Roles and Ownership

| Role | Responsibility |
|------|----------------|
| Core Reliability Owner | CH/PI packages, P0/P1 prioritization |
| Sketch & UX Owner | SU/UX packages, consistency |
| Printability Owner | PR packages, export trust |
| QA & Release Owner | Gates, CI, burn-in |
| Architecture Owner | AR packages, refactoring |

---

## Contact

For questions about this plan:
- Technical issues: Contact relevant workstream owner
- Process issues: Contact QA & Release Owner
- Scope questions: Review [V1 Charter](roadmap_ctp/v1/01_V1_CHARTER_AND_NON_NEGOTIABLES.md)

---

## Change Log

| Date | Version | Change |
|------|---------|--------|
| 2026-02-22 | 1.0.0 | Initial V1 planning reset |

---

**This plan is the authoritative source for V1 production readiness. All decisions must reference this document set.**
