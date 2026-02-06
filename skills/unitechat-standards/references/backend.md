# Backend Standards (UniteChat)

## Goals

- Predictable behavior
- Low regression risk
- Easy-to-read data flow

## Python Code Style

- Prefer small, single-purpose functions.
- Use clear names over clever compression.
- Add type hints for public functions and non-trivial internals.
- Keep error handling explicit and scoped.

## Data + Parsing

- Normalize external/variant inputs at boundaries.
- Avoid implicit assumptions about missing fields.
- Validate shape before transformation.
- Keep parser behavior deterministic and testable.

## API + Routes

- Keep routes thin; move logic into service/helper functions.
- Return stable response shapes.
- Preserve backward compatibility for existing fields whenever possible.

## Safety

- Do not silently swallow critical exceptions.
- Log actionable errors with context, not noisy dumps.
- Avoid hidden side effects in utility functions.

## Performance

- Prefer bounded operations for large scans/parsing.
- Cache only where invalidation behavior is clear.

## Review Checklist

- Is each function doing one clear thing?
- Are edge cases and null/empty inputs handled explicitly?
- Are response structures stable for frontend callers?
- Did we validate behavior with targeted checks?
