# 02 Design System

## Purpose
Describe the actual UI language and interaction style currently used.

## Status
- [Confirmed from code] No formal design system exists.
- [Strongly inferred] Visual consistency comes from native macOS controls via `rumps`.

## Confirmed from code
- Menu bar icon/title string is dynamically updated (`monitor.py:380`, `monitor.py:488`).
- Menu is text-driven with separators and action items (`monitor.py:391-406`).
- Setup/settings use modal text-input windows (`monitor.py:417-453`, `monitor.py:580-627`).
- Progress visualization is text glyph based (`monitor.py:327-331`, `monitor.py:494`).

## Inferred / proposed
- [Strongly inferred] Visual aesthetic: utilitarian, minimal, native macOS utility style.
- [Strongly inferred] Typography/colors/spacing are system defaults controlled by macOS, not custom CSS/theme tokens.
- [Not found in repository] No component library, design tokens, icon system, motion system, or brand guideline docs.

## Important details
- UI consistency is high because the surface area is small and native.
- Information density is optimized for quick glanceability in menu bar text.
- Interaction model is modal and linear (one prompt at a time).

## Open issues / gaps
- No explicit accessibility audit (contrast, screen reader labels, keyboard flow).
- No affordance for richer diagnostics without opening external logs.
- String-heavy UX may be hard for first-time users without inline help.

## Recommended next steps
- Add concise help text entry in menu for data source assumptions.
- Add optional compact "details" window with richer but still native formatting.
- Document UI copy conventions to keep prompts consistent.
