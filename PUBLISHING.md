# Publishing cura-hybrid-supports (GitHub Desktop on the Mac)

This file lives inside the repo so it can't get separated from the zip. The `cura-hybrid-supports` folder is a ready git repo on `main` with the tag `v0.6.6-wip`, committed as Matthew Armstrong <The-Dorkknight@users.noreply.github.com>.

## 0. Try it in Cura first (Linux Mint, or any computer with Cura)

Close Cura. In the `cura-hybrid-supports` folder double-click `Install-Linux.sh` (choose **Run** if asked), `Install-Windows.bat` or `Install-Mac.command`. Press **Install / Update**, then **Start Cura**; the row turns green with a tick once Cura has loaded the plugin. It replaces any older Hybrid Supports. In Cura it is under **Extensions > Hybrid Supports** and, with a model loaded and selected, at the bottom of the left tool bar (**H**).

Then **re-generate** supports on any part that had older supports: old meshes don't carry the fix for Elegoo's *Minimum Support Area*.

If double-clicking the `.sh` opens it in a text editor: right-click it > Properties > Permissions > tick "Allow executing file as program". On the Mac, right-click `Install-Mac.command` > Open the first time. The Windows and Mac launchers have not been tested yet.

## Already published an earlier version?

- **Not published yet:** carry on with step 1.
- **Already published from an earlier zip:** in Finder, copy everything inside this new `cura-hybrid-supports` folder over your existing one (replace all, but keep your existing hidden `.git` folder if Finder asks), then in GitHub Desktop write a summary such as "0.6.6-wip: tether span limits", **Commit to main** and **Push origin**. On github.com, mark any older release as superseded or delete it, then run the *release* workflow with `v0.6.6-wip` (step 2.2).
  - Or simpler: delete the repo on github.com (Settings > Danger Zone), delete your local copy, and publish this folder fresh with step 1. This keeps the history clean.

## 1. Publish

1. Unzip, then drag the `cura-hybrid-supports` folder onto GitHub Desktop (or **File > Add Local Repository**).
2. Click **Publish repository**. Name: `cura-hybrid-supports`. **Untick "Keep this code private".**
3. Click **Publish**.

## 2. One-time steps in the browser (github.com/The-Dorkknight/cura-hybrid-supports)

1. **Pages:** Settings > Pages > Source *Deploy from a branch*, Branch `main`, folder `/docs`, Save. A minute later the site is at https://The-Dorkknight.github.io/cura-hybrid-supports/
2. **Release:** GitHub Desktop may not push the tag. Open **Actions > release > Run workflow**, enter `v0.6.6-wip`, Run. That builds the `.curapackage` and plugin zip and creates a **pre-release** with them attached. (If the tag did get pushed, this already ran on its own.)
3. **Actions:** check *build* and *release* are green. They haven't been run on GitHub before, so a first-run failure is possible; the log will say why.
4. Optional: Settings > General > Social preview > upload `docs/images/icon-512.png`.

## 3. Avatar check

If the commit on GitHub shows no avatar, GitHub doesn't recognise the no-reply address. Find yours in Settings > Emails (it looks like `12345678+The-Dorkknight@users.noreply.github.com`), then in GitHub Desktop open **Repository > Open in Terminal** and run:

```
git config user.email 12345678+The-Dorkknight@users.noreply.github.com
git rebase --root --exec "git commit --amend --reset-author --no-edit"
git tag -f -a v0.6.6-wip -m "Hybrid Supports 0.6.6-wip (work in progress)"
git push --force origin main
git push --force origin v0.6.6-wip
```

Best done before anyone else clones it.

## What's in the repo

| File | What |
|---|---|
| `README.md` | Front page: what it does, install, settings, honest test status |
| `HOW_IT_WORKS.md` | The pipeline in detail |
| `docs/RESEARCH.md` | All research notes: paint-on supports, how CuraEngine treats support meshes, why 0.1.x failed on the box, the bridge-span maths |
| `CHANGELOG.md` | What changed in each version |
| `PUBLISHING.md` | This file |
| `test-prints/` | One Neptune 4 G-code with every head on a 40 mm channel and corner, and the parts |
| `docs/index.html` | The GitHub Pages site |

## Later updates

Edit, then in GitHub Desktop: write a summary, **Commit to main**, **Push origin**. For a new release, bump `__version__` in `HybridSupports/hybrid_core.py` and `version` in `HybridSupports/plugin.json`, add a CHANGELOG entry, run `python3 -m pytest tests -q` and `tests/cura_harness/run_in_cura.sh` against a real Cura (see README, Development), then run the *release* workflow with the new tag (e.g. `v0.6.6-wip`).

## Photos of real prints

The Pages site has a hidden "Real prints" section that appears by itself once these exist:

| File | What |
|---|---|
| `docs/images/print-1.jpg` | Print with hybrid supports still on |
| `docs/images/print-2.jpg` | Same part with supports removed |

Resize to about 1600 px wide and strip EXIF/GPS first (`exiftool -all= print-1.jpg`), then commit and push. To show them in the README too, add `![Print](docs/images/print-1.jpg)` under the renders.

## Alternative: command line

```
cd cura-hybrid-supports
gh auth login
gh repo create cura-hybrid-supports --public --source . --push
git push origin v0.6.6-wip
```
