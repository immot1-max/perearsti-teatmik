#!/usr/bin/env bash
# Töövoo teade GitHubi issue'na. Kui sama algusega pealkirjaga issue on juba lahti, lisatakse sinna kommentaar,
# et korduv tõrge ei tekitaks iga käivitusega uut issue't.
# Kasutus: teata.sh "<pealkirja püsiv algus>" "<uue issue pealkiri>" <sisu fail>
set -u
algus="$1"; pealkiri="$2"; fail="$3"
nr=$(gh issue list --state open --search "\"$algus\" in:title" --json number,title \
      --jq "[.[] | select(.title | startswith(\"$algus\"))][0].number // empty" 2>/dev/null || true)
if [ -n "$nr" ]; then
  { echo "**$(date +%d.%m.%Y)**"; echo; cat "$fail"; } > "$fail.kommentaar"
  gh issue comment "$nr" --body-file "$fail.kommentaar" && exit 0
fi
gh issue create --title "$pealkiri" --body-file "$fail"
