---
type: architecture
updated: ⟨YYYY-MM-DD⟩
---

# Architecture: ⟨topic, e.g. Overview / Data Flow / Auth⟩

> **TL;DR:** ⟨the whole thing in 2–3 sentences, so this note is useful even if
> only the top is loaded.⟩

## The shape
⟨Boxes-and-arrows in words or a fenced ASCII/mermaid diagram. What talks to what.⟩

```
⟨client⟩ → ⟨edge⟩ → ⟨service⟩ → ⟨store⟩
```

## Why it's shaped this way
⟨Constraints and history that explain the design. Link ADRs.⟩

## Invariants (things that must stay true)
- ⟨e.g. "all writes go through the repository layer"⟩

## Where things live (map into the repo)
- ⟨component⟩ → `⟨path⟩`

## Related
- ⟨[[20-Modules/…]]⟩ · ⟨[[30-Decisions/…]]⟩
