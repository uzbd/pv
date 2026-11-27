# Changelog

## 2.5.0

- Replaced the multi-page frontend with one mobile-first chat room homepage.
- Changed the visual palette to pure AMOLED black with grayscale bubbles, controls, and settings.
- Reduced Settings to exactly Text Scaling, Export, and Import.
- Added one global text scaling preference (80%–150%) that persists in local browser storage and applies across the UI.
- Simplified Export to one JSONL download and Import to a single JSON/JSONL file picker.
- Added immediate optimistic message bubbles and automatic loading of older messages on scroll.
- Removed React Query, Lucide icons, and Tailwind from the frontend dependency set.
- Kept the existing FastAPI authentication, GitHub/Google Drive storage adapters, dual-store mirroring, JSONL format, and merge behavior.
