# Retrofit Patterns

> Patterns for modernising legacy systems
> **Updated:** 2025-12-09

---

## 📑 Index

### Modernisation Patterns
1. [Strangler Fig Pattern](#1-strangler-fig-pattern)
2. [Branch by Abstraction](#2-branch-by-abstraction)
3. [Parallel Run](#3-parallel-run)
4. [Anti-Corruption Layer](#4-anti-corruption-layer)
5. [Database Refactoring Patterns](#5-database-refactoring-patterns)
   - [Transition Period](#51-transition-period)
   - [Expand-Contract](#52-expand-contract-pattern)
6. [Feature Toggles (Feature Flags)](#6-feature-toggles-feature-flags)
7. [Incremental Migration](#7-incremental-migration)
8. [Blue-Green Deployment](#8-blue-green-deployment)

### Decision Trees
- [Level 1: Project Context](#level-1-project-context)
- [TREE A: Full System](#tree-a-full-system)
- [TREE B: Dependencies/Technology](#tree-b-dependenciestechnology)
- [TREE C: Database Migration](#tree-c-database-migration)
- [TREE D: Deployment Strategy](#tree-d-deployment-strategy)

### Resources
- [Pattern Comparison](#-pattern-comparison)
- [Quick Decision Matrix](#-quick-decision-matrix)
- [Warning Signs](#-warning-signs)
- [References](#-references)

---

## 1. Strangler Fig Pattern

**Concept:** Gradually replace legacy functionality with a new system.

```
Legacy System          New System
┌─────────────┐       ┌─────────────┐
│ Feature A   │  -->  │ Feature A   │ ✅
│ Feature B   │       │ Feature B   │ ✅
│ Feature C   │ ◄──   │             │
│ Feature D   │ ◄──   │             │
└─────────────┘       └─────────────┘
```

**Application:**
- Migrate feature by feature
- API Gateway routing decides which system handles the request
- Legacy and new coexist temporarily

**Example:**
```
Client → API Gateway → [Feature A → New]
                      → [Feature B → New]
                      → [Feature C → Legacy]
```

**When:**
- Large system that cannot be replaced all at once
- You need to deliver incremental value
- Low risk

---

## 2. Branch by Abstraction

**Concept:** Create an abstraction that allows switching between old/new implementations.

```java
// Abstraction
interface PaymentService {
    void processPayment(Order order);
}

// Implementations
class LegacyPayment implements PaymentService { }
class NewPayment implements PaymentService { }

// Switching
PaymentService payment = featureFlag.enabled()
    ? new NewPayment()
    : new LegacyPayment();
```

**Application:**
- Large changes in a single codebase
- Production testing with feature flags
- Instant rollback

**When:**
- Changing a critical dependency
- Large refactor without long-lived branches
- A/B testing of implementations

---

## 3. Parallel Run

**Concept:** Run legacy and new in parallel, compare results.

```
Request
   │
   ├──> Legacy System ──> Result A ┐
   │                                ├─> Comparator → Log differences
   └──> New System ───> Result B ──┘
                            │
                         Return B
```

**Application:**
- Run both systems
- Use the result from the new system
- Compare and log differences
- Detect bugs before full switchover

**When:**
- Critical business logic
- High confidence required before switchover
- Sensitive data (financial, medical)

---

## 4. Anti-Corruption Layer

**Concept:** Translation layer between legacy and new to isolate models.

```
New System          ACL              Legacy System
┌──────────┐    ┌────────┐          ┌──────────┐
│ Customer │<-->│Adapter │<-------->│ CLIENTE  │
│  .name   │    │        │          │  .NOMBRE │
│  .email  │    │Translate│          │  .EMAIL  │
└──────────┘    └────────┘          └──────────┘
```

**Application:**
```java
class CustomerAdapter {
    Customer toNewModel(ClienteLegacy legacy) {
        return new Customer(
            name: legacy.NOMBRE,
            email: legacy.EMAIL
        );
    }
}
```

**When:**
- Legacy with a poor data model
- Avoid contaminating the new system
- Different bounded contexts

---

## 5. Database Refactoring Patterns

### 5.1 Transition Period

**Concept:** Maintain old and new schema during migration.

```sql
-- Phase 1: Add new column
ALTER TABLE customers ADD email_address VARCHAR2(100);

-- Phase 2: Dual write (old + new)
UPDATE customers SET
    email = :email,           -- Old
    email_address = :email;   -- New

-- Phase 3: Migrate data
UPDATE customers SET email_address = email WHERE email_address IS NULL;

-- Phase 4: Switchover (use new column)
-- Phase 5: Remove old column
ALTER TABLE customers DROP COLUMN email;
```

**Steps:**
1. Add new (without breaking anything)
2. Dual write
3. Migrate existing data
4. Switchover
5. Remove old

### 5.2 Expand-Contract Pattern

```
Expand: Add new structure without removing old
  ↓
Migrate: Move data and dual write
  ↓
Contract: Remove old structure
```

---

## 6. Feature Toggles (Feature Flags)

**Concept:** Enable/disable features at runtime without deployment.

```java
if (featureFlags.isEnabled("new_checkout", userId)) {
    return newCheckoutService.process(order);
} else {
    return legacyCheckoutService.process(order);
}
```

**Types:**
- **Release toggles:** Gradual deployment control
- **Experiment toggles:** A/B testing
- **Ops toggles:** Circuit breakers, kill switches
- **Permission toggles:** Per user/role

**Application:**
```yaml
features:
  new_checkout:
    enabled: true
    rollout: 10%  # 10% of users
    whitelist:
      - user_12345
      - beta_testers
```

**When:**
- Frequent deploys with incomplete features
- Canary releases
- A/B testing
- Kill switch for problematic features

---

## 7. Incremental Migration

**Concept:** Migrate by layer/module in dependency order.

```
Migration by layer:
┌──────────────────────────┐
│ UI Layer                 │ ← Phase 3
├──────────────────────────┤
│ Business Logic           │ ← Phase 2
├──────────────────────────┤
│ Data Access / Repository │ ← Phase 1
├──────────────────────────┤
│ Database                 │ ← Phase 0
└──────────────────────────┘

Or by bounded context:
[Orders] → [Customers] → [Inventory] → [Billing]
```

**Strategy:**
1. Identify independent modules
2. Create migration order (dependencies)
3. Migrate bottom-up or module by module
4. Integrate with legacy via APIs

**When:**
- System with well-separated modules
- You cannot do Big Bang
- You want to deliver value incrementally

---

## 8. Blue-Green Deployment

**Concept:** Two identical environments, instant switch between them.

```
Production Traffic
       │
       ▼
   [Router]
       │
       ├──> Blue (Current v1.0)  ✅ Active
       │
       └──> Green (New v2.0)     🟢 Standby

-- Deploy new to Green --
-- Test on Green --
-- Switch router --

Production Traffic
       │
       ▼
   [Router]
       │
       ├──> Blue (Old v1.0)      🔵 Standby
       │
       └──> Green (Current v2.0) ✅ Active
```

**Application:**
- Deploy v2 to the Green environment
- Full testing
- Switch DNS/Load Balancer
- Instant rollback if it fails

**When:**
- Zero downtime required
- Fast rollback is critical
- Pre-production testing on exact replica

---

## 📊 Pattern Comparison

| Pattern | Complexity | Risk | Rollback | Common Use |
|---------|------------|------|----------|------------|
| Strangler Fig | Medium | Low | Easy | Monolith → Microservices |
| Branch by Abstraction | Low | Low | Instant | Dependency change |
| Parallel Run | High | Very Low | N/A | Critical logic |
| Anti-Corruption | Medium | Low | N/A | Legacy integration |
| Database Refactoring | Medium | Medium | Hard | Schema changes |
| Feature Toggles | Low | Low | Instant | Continuous Delivery |
| Incremental | Low | Low | Per module | Gradual migration |
| Blue-Green | Medium | Low | Instant | Zero downtime |

---

## 🎯 Complete Decision Tree

### Level 1: Project Context

```
What type of change do you need?
│
├─ Replace entire system → TREE A
├─ Change dependency/technology → TREE B
├─ Migrate database → TREE C
├─ Deploy new version → TREE D
└─ Testing/Validation → Feature Toggles + Parallel Run
```

---

### TREE A: Full System

```
What is the system size?
│
├─ SMALL (<10K users, <100K LOC)
│  │
│  ├─ Is downtime acceptable? (>4h)
│  │  ├─ YES → Big Bang
│  │  └─ NO → Blue-Green Deployment
│  │
│  └─ Is it a critical system?
│     ├─ YES → Phased + Parallel Run
│     └─ NO → Big Bang or Phased
│
├─ MEDIUM (10K-100K users, 100K-500K LOC)
│  │
│  ├─ Is the system modular?
│  │  ├─ YES → Migrate by?
│  │  │     ├─ Feature → Strangler Fig
│  │  │     └─ Layer → Chicken Little
│  │  │
│  │  └─ NO → Phased Migration
│  │        ├─ Phase 1: Read-only
│  │        ├─ Phase 2: Simple CRUD
│  │        └─ Phase 3: Business Logic
│  │
│  └─ Budget?
│     ├─ Limited → Phased
│     └─ Ample → Butterfly
│
└─ LARGE (>100K users, >500K LOC)
   │
   ├─ Fault tolerance?
   │  ├─ ZERO (banking, health) → Butterfly Migration
   │  │                            ├─ Bidirectional sync
   │  │                            ├─ Trickle: 1%→5%→25%→100%
   │  │                            └─ Parallel Run validation
   │  │
   │  ├─ LOW (1% error ok) → Strangler Fig + Trickle
   │  │                       ├─ Feature by feature
   │  │                       ├─ 10% users/week
   │  │                       └─ Anti-Corruption Layer
   │  │
   │  └─ MEDIUM (5% error ok) → Phased + Canary
   │                           ├─ Per bounded context
   │                           └─ Gradual rollout
   │
   └─ Team available?
      ├─ 1-3 devs → Incremental (small steps)
      ├─ 4-10 devs → Strangler Fig + Phased
      └─ >10 devs → Multiple teams per feature
```

---

### TREE B: Dependencies/Technology

```
What are you changing?
│
├─ ORM / Data Access
│  └─ Branch by Abstraction
│     ├─ Create interface
│     ├─ Feature flag switch
│     └─ Rollout: 1%→10%→50%→100%
│
├─ Framework (React→Vue, Spring→Quarkus)
│  │
│  ├─ Is the change compatible?
│  │  ├─ YES → Branch by Abstraction
│  │  └─ NO → Strangler Fig (new service)
│  │
│  └─ UI framework?
│     ├─ YES → Micro-frontends + Strangler Fig
│     └─ NO → Branch by Abstraction
│
├─ Cloud Provider (AWS→Azure)
│  └─ Blue-Green + Butterfly
│     ├─ Setup Azure environment
│     ├─ Data sync AWS↔Azure
│     ├─ Test in Azure
│     └─ DNS switch
│
├─ External API/Service
│  └─ Anti-Corruption Layer + Branch by Abstraction
│     ├─ Adapter for old API
│     ├─ Adapter for new API
│     ├─ Feature flag to switch
│     └─ Parallel run (validate)
│
└─ Library/Package upgrade
   │
   ├─ Breaking changes?
   │  ├─ YES → Branch by Abstraction
   │  └─ NO → Direct upgrade + testing
   │
   └─ Risk?
      ├─ High → Feature flag + canary
      └─ Low → Direct upgrade
```

---

### TREE C: Database Migration

```
Type of DB change?
│
├─ Full engine change (Oracle→Postgres)
│  │
│  └─ Is downtime acceptable?
│     │
│     ├─ YES (>12h) → Big Bang
│     │              ├─ Full backup
│     │              ├─ Export/Import data
│     │              └─ Validation queries
│     │
│     └─ NO → Butterfly + Replication
│            ├─ Setup new DB
│            ├─ Continuous replication (GoldenGate/Debezium)
│            ├─ Dual write application
│            ├─ Validation & reconciliation
│            └─ Cutover when sync OK
│
│     └─ Alternative → Chicken Little (by layers)
│                      ├─ Layer 1: Data Access
│                      ├─ Layer 2: Services
│                      ├─ Layer 3: APIs
│                      └─ Layer 4: UI
│
├─ Schema Refactoring (columns, tables)
│  └─ Expand-Contract Pattern
│     ├─ EXPAND: ADD COLUMN new_col
│     ├─ MIGRATE: Dual write + backfill
│     ├─ CONTRACT: DROP COLUMN old_col
│     └─ Timing: 2-4 weeks/phase
│
├─ Normalisation/Denormalisation
│  └─ Transition Period
│     ├─ Create normalised table
│     ├─ Trigger dual write
│     ├─ Migrate data (batch)
│     ├─ Change queries
│     └─ Drop old table
│
└─ Partitioning/Sharding
   └─ Online Redefinition (DBMS_REDEFINITION)
      ├─ Zero downtime
      ├─ Online during process
      └─ Automatic sync
```

---

### TREE D: Deployment Strategy

```
Type of deployment?
│
├─ New feature
│  │
│  ├─ Complete or incremental feature?
│  │  │
│  │  ├─ Complete → Feature Toggle
│  │  │             ├─ Deploy with flag OFF
│  │  │             ├─ Enable for beta users
│  │  │             ├─ Rollout: 1%→10%→50%→100%
│  │  │             └─ Remove flag when stable
│  │  │
│  │  └─ Incremental → Strangler Fig
│  │                   ├─ Part 1: read-only
│  │                   ├─ Part 2: write
│  │                   └─ Part 3: complete
│  │
│  └─ Do you need A/B testing?
│     │
│     ├─ YES → Feature Toggle (experiment type)
│     │       ├─ Variant A: 50% users
│     │       ├─ Variant B: 50% users
│     │       └─ Measure & decide
│     │
│     └─ NO → Canary Deployment
│            ├─ 5% traffic → v2
│            ├─ Monitor metrics
│            ├─ 25%→50%→100%
│            └─ Auto rollback on errors
│
├─ Critical change (payment, auth)
│  └─ Parallel Run + Blue-Green
│     ├─ Deploy v2 to Green
│     ├─ Run both in parallel
│     ├─ Compare results
│     ├─ Log differences
│     ├─ Fix bugs in Green
│     └─ Switch when 99.9% match
│
├─ Hotfix/Bugfix
│  │
│  ├─ Impact?
│  │  ├─ High → Blue-Green (instant rollback)
│  │  └─ Low → Direct deploy + canary
│  │
│  └─ Urgency?
│     ├─ Critical → Direct deploy with backup
│     └─ Normal → Canary (10%→50%→100%)
│
└─ Infrastructure change
   └─ Blue-Green + Canary
      ├─ Setup Blue (new infra)
      ├─ Deploy app to Blue
      ├─ Route 10% traffic
      ├─ Monitor performance
      └─ Gradual rollout
```

---

### 🎯 Quick Decision Matrix

**Choose your pattern in 30 seconds:**

| If you have... | Use... |
|----------------|--------|
| Small system + downtime OK | **Big Bang** |
| Small system + zero downtime | **Blue-Green** |
| Large + modular system | **Strangler Fig** |
| Large + monolithic system | **Phased Migration** |
| Dependency change | **Branch by Abstraction** |
| Critical logic (banking) | **Parallel Run** |
| Schema changes | **Expand-Contract** |
| New feature | **Feature Toggle** |
| Zero-downtime deploy | **Blue-Green** |
| Legacy with poor design | **Anti-Corruption Layer** |
| DB migration | **Butterfly** or **Chicken Little** |
| A/B testing | **Feature Toggle (experiment)** |

---

### 🚦 Warning Signs

**❌ Do NOT use Big Bang if:**
- System has >10K active users
- Zero downtime required
- Critical data (financial, health)
- Rollback is hard/impossible

**❌ Do NOT use Butterfly if:**
- Limited budget (dual run is expensive)
- Team < 5 people
- Simple data synchronisation

**❌ Do NOT use Feature Toggles if:**
- Permanent toggle (technical debt)
- Too many toggles (>10 active = complexity)
- Simple testing (no A/B needed)

**✅ COMBINE patterns when:**
- Large project (Strangler Fig + Trickle + Blue-Green)
- Different areas need different strategies
- Very high risk (multiple safety nets)

---

## 🔗 References

- [Martin Fowler - Strangler Fig](https://martinfowler.com/bliki/StranglerFigApplication.html)
- [Refactoring Databases - Scott Ambler](https://databaserefactoring.com/)
- [Feature Toggles - Pete Hodgson](https://martinfowler.com/articles/feature-toggles.html)
