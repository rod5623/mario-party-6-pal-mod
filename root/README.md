# root/

Put your extracted game here, as exported by GameCube Rebuilder (GCR) from your own GP6P01
disc:

```
root/
  &&systemdata/Start.dol
  data/
  dll/
  mess/
  movie/
  sound/
  ...
```

The board patches edit `root/data` directly. Copy the other outputs in from
`src/build/GP6P01/` (see the top-level README). Then rebuild an ISO from this folder with
`python -m tools.scripts.build_iso` (from `src/`) and run it in Dolphin. Every file here that
isn't on the original disc is added to the ISO, so don't leave backups or notes in this folder.

Keep a clean copy of this folder outside the repo so you can undo the patches. Nothing here
except this README is tracked by git.
