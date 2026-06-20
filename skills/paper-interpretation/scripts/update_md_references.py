#!/usr/bin/env python3
"""
Update old figure path references in a markdown file to new ones.

Use case: when you re-extract figures with a different naming scheme
(e.g. fullpage_NNN.png → Figure_X_Y_Z.png), you need to update all the
existing markdown references in your interpretation file.

Usage:
    python3 update_md_references.py <md_file> <mapping.json>

Where mapping.json is a JSON object like:
    {
      "fullpage_027": "Figure_2_2_5_2_A",
      "fullpage_029": "Figure_2_2_5_4_A",
      ...
    }

Or interactive mode:
    python3 update_md_references.py <md_file> --interactive

This walks through each old reference in the file and asks you for the new name.

The script:
1. Backs up the original to <md_file>.bak
2. Replaces all `<old>.png` references with `<new>.png`
3. Removes whole image lines for entries mapped to empty string ""
   (use this for stale references that no longer have a figure)
4. Reports how many lines were changed / removed
"""

import json, re, shutil, sys, os


def load_mapping(path):
    if path.endswith('.json'):
        with open(path) as f:
            return json.load(f)
    raise ValueError('Mapping file must be .json')


def apply_mapping(md_path, mapping, dry_run=False):
    with open(md_path) as f:
        text = f.read()

    new_lines = []
    changed = 0
    removed = 0
    for line in text.split('\n'):
        new = line
        # Detect entries marked for deletion (empty new value)
        delete_this = False
        for old, repl in mapping.items():
            if old in new:
                if repl == '' or repl is None:
                    if new.lstrip().startswith('!['):
                        delete_this = True
                        break
                else:
                    new2 = re.sub(rf'{re.escape(old)}(?:_hires)?\.png', f'{repl}.png', new)
                    if new2 != new:
                        new = new2
                        changed += 1
        if delete_this:
            removed += 1
            continue
        new_lines.append(new)

    new_text = '\n'.join(new_lines)
    if dry_run:
        print(f'[DRY RUN] Would change {changed} lines, remove {removed} lines')
        return changed, removed

    # Backup
    bak = md_path + '.bak'
    shutil.copy(md_path, bak)
    with open(md_path, 'w') as f:
        f.write(new_text)

    print(f'Updated {md_path} (backup: {bak})')
    print(f'  Changed:  {changed} references')
    print(f'  Removed:  {removed} obsolete image lines')
    return changed, removed


def interactive_mode(md_path):
    """Walk through unique old references and prompt for new names."""
    with open(md_path) as f:
        text = f.read()

    # Find all *.png references
    pattern = re.compile(r'\(([^)\s]+\.png)\)')
    refs = sorted(set(pattern.findall(text)))
    if not refs:
        print('No image references found.')
        return

    print(f'Found {len(refs)} unique image references.')
    print('For each, enter:')
    print('  - new filename (without .png) → rename')
    print('  - empty string → delete the line')
    print('  - "skip" or just press enter → leave unchanged')
    print()

    mapping = {}
    for r in refs:
        base = os.path.splitext(os.path.basename(r))[0]
        ans = input(f'{r} → ').strip()
        if not ans or ans == 'skip':
            continue
        if ans == 'del':
            mapping[base] = ''
        else:
            mapping[base] = ans

    if not mapping:
        print('No changes.')
        return

    print()
    print('Mapping to apply:')
    for k, v in mapping.items():
        print(f'  {k} → {v if v else "(DELETE)"}')
    confirm = input('Apply? [y/N] ').strip().lower()
    if confirm != 'y':
        print('Aborted.')
        return

    apply_mapping(md_path, mapping)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage:', file=sys.stderr)
        print('  update_md_references.py <md_file> <mapping.json>', file=sys.stderr)
        print('  update_md_references.py <md_file> --interactive', file=sys.stderr)
        print('  update_md_references.py <md_file> <mapping.json> --dry-run', file=sys.stderr)
        sys.exit(1)

    md_file = sys.argv[1]
    if len(sys.argv) >= 3 and sys.argv[2] == '--interactive':
        interactive_mode(md_file)
    elif len(sys.argv) >= 3:
        mapping = load_mapping(sys.argv[2])
        dry = '--dry-run' in sys.argv
        apply_mapping(md_file, mapping, dry_run=dry)
    else:
        print('Need either a mapping file or --interactive', file=sys.stderr)
        sys.exit(1)
