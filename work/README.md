# Work Directory

This directory is for development work, test novels, and experiments. It's gitignored to keep the repository clean.

## Structure

```
work/
├── recent_projects.json  # Tracks recently accessed projects (auto-generated)
├── novels/               # Test story projects generated during development
├── experiments/          # Quick experiments and prototypes
└── scratch/              # Temporary files and one-off tests
```

## Usage

### Creating Test Novels

```bash
# Create a test novel in the work directory
./venv/bin/novel new my-test-story --dir work/novels

# Run ticks
./venv/bin/novel tick --project work/novels/my-test-story
./venv/bin/novel run --n 10 --project work/novels/my-test-story
```

### Benefits vs /tmp

- **Persistent**: Survives system reboots
- **Organized**: All test projects in one place
- **Accessible**: Easy to inspect and debug
- **Gitignored**: Won't clutter version control

## Examples

```bash
# Test the name generator
./venv/bin/novel new name-test --dir work/novels
./venv/bin/novel run --n 5 --project work/novels/name-test

# Test two-phase tick implementation
./venv/bin/novel new two-phase-test --dir work/novels
./venv/bin/novel tick --project work/novels/two-phase-test

# Quick experiments
./venv/bin/python -c "from novel_agent.tools.name_generator import NameGenerator; ..." > work/scratch/names.txt
```

## Cleanup

Since this directory is gitignored, you can safely delete its contents anytime:

```bash
# Remove all test novels
rm -rf work/novels/*

# Remove all experiments
rm -rf work/experiments/*

# Clean everything
rm -rf work/*/
```

## Note

This directory is **not tracked by git**. Only this README is committed to help new developers understand the structure.
