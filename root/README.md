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
`src/build/GP6P01/` (see the top-level README). Then rebuild an ISO from this folder with GCR, then you can run the iso with dolphin.

Keep a clean copy of this folder outside the repo so you can undo the patches. Nothing here
except this README is tracked by git.
