# Intensifier/hyperbole word list and litmus test

Copied from the rmtool-dev repository's `docs/dev/INTENSIFIER_SANITIZATION.md`
(methodology and exceptions only; that file's rmtool-specific scope
decisions and per-file checklist are omitted). Standing rule: no
emphasis/intensifier words in docs, comments, commit messages or
printed messages; state facts plainly.

## Methodology

**Word list checked** (base form + derived forms, case-insensitive,
whole-word): real/really, genuine(ly), actual(ly), true/truly,
literal(ly), indeed, certainly, definitely, positively, undoubtedly,
clearly, obvious(ly), very, extreme(ly), absolute(ly), completely,
totally, utter(ly), entirely, wholly, thorough(ly), highly, deeply,
greatly, fully, perfectly, remarkable/remarkably, exceptional(ly),
particularly, especially, significant(ly), substantial(ly),
enormous(ly), immense(ly), tremendous(ly), vast(ly), huge(ly),
massive(ly), incredible/incredibly, unbelievable/unbelievably,
amazing(ly), surprising(ly), super, mega, ultra, crazy/crazily,
insane(ly), ridiculous(ly), wicked(ly), hella, terribly, awfully,
dreadfully, downright, seriously, honestly, plain, purely, simply.

**What counts as "prose" for this sweep:** for `.md`/`.txt`/`.cff`/
`.rst` files, the whole file. For code files, **comments only** --
`!`-to-end-of-line for free-form Fortran (`.f90`), `#`-to-end-of-line
for Python/shell/YAML/cfg -- never the code itself. This matters
concretely: a raw whole-file grep for "real"/"true" returns thousands
of false positives from Fortran's `real` type-declaration keyword and
`.true.`/`.false.` logical literals, which are language syntax, not
English prose. (Caught directly this session: an initial whole-file
count came back at ~9500 hits; restricting to comment text alone cut
it to ~4700, and that gap was entirely this false-positive class, not
real findings.)

**Second false-positive class, found while reviewing `src/rmclean/`:**
a comment-line extractor can't distinguish genuine prose from
commented-out *code* -- both start with `!` in free-form Fortran. A
disabled line like `!xarr(i) = real(i)` or `!real*8 vel_light`
contains Fortran's `real` keyword, not an English word, and is not a
prose finding either. Handled by reading each hit in context (as
already done throughout this file) rather than trying to regex this
away structurally.

**Third note, found while reviewing `build.sh`:** the per-file counts
above only scanned `#`/`!` comment text, not string literals passed to
`echo`/`print`/error messages -- but those are prose a human reads too
(an error message is still writing). Caught one extra instance this
way (an `echo`d `$RMTOOL_HOME` mismatch error) beyond what the count
said to expect. The counts above are therefore a floor, not an exact
ceiling, for shell/Python files specifically -- apply the same litmus
test to any such string encountered while reviewing a file, even if
it's not one of the lines the original count flagged.

**Litmus test for each hit, applied per-instance, not blanket-deleted:**
does removing the word lose real information a careful reader would
want, or is it pure filler restating what the sentence already states
plainly? Categories already found to be **legitimate, keep as-is**:
- real (observational/survey) data vs. this repo's own synthetic test
  fixtures -- a genuine, load-bearing distinction used throughout
- "real"/"imaginary" as the literal complex-number output components
  (`output_mode=ri`, `REAL.RMCUBE.FITS`), "real-space" as the literal
  opposite of Fourier/frequency-space -- domain math terms
- "true"/"false" documenting a config parser's literal accepted
  boolean values; grammatical "true of every tool" (= applies to)
- literal identifiers containing these words verbatim (a CLI flag like
  `--actual-log`, a FITS filename literal) -- never rename an actual
  flag/filename during a prose cleanup
- "real" (confirmed, actually happened/actually production-scale) vs.
  a hypothetical/simulated/toy case being explicitly contrasted nearby
  -- common in this codebase's own incident-report-style comments
  ("a real SIGSEGV," "a real full-cube run"); kept where the contrast
  is the point, cut where it's redundant filler (e.g. the sentence
  already says "not X" elsewhere, or nothing hypothetical is nearby to
  contrast against at all)
- "real"/"genuinely" contrasting an actual production code path
  against a throwaway simulation of it -- found densely in
  `rmclean_cubes.f90`'s Belady-cache advisory subroutine (`real Pass 1`
  vs. its own throwaway simulated cache; `REAL production use`/`REAL
  multi-thread speedup` vs. the same subroutine's forced-single-
  threaded timing measurement, ~3.6x discrepancy quantified). Kept
  where the sentence's whole point is real-vs-simulated; cut where
  "real"/"genuinely" only decorates a Pass-1 reference already
  disambiguated by an adjacent, explicitly-named "Pass 0" in the same
  comment (redundant with the Pass-numbering itself, same rule as the
  Pass-0/Pass-1 entry above).
- "true"/"absolute"/"perfectly"/"extreme" as precise mathematical or
  statistical terms of art, not emphasis -- found densely in
  `rmclean.f90`'s peak-fitting/noise-estimation comments: "true value"
  vs. an estimator's biased output (standard statistics usage),
  "absolute index" vs. a local/relative offset (a real algorithmic
  distinction, not hedging), "perfectly flat/linear/clean" naming an
  exact degenerate case in a fit (zero measure, not hyperbole),
  "extreme values" meaning statistical extrema (min/max), same as the
  already-noted `src/rmclean/quad_interp.f.f90` precedent. Rule of
  thumb: if the word is the technical term itself (removing it would
  force a different, longer technical phrase to stand in), keep it;
  if it's decorating an already-precise technical term for emphasis
  ("a real, accepted cost," "a genuine sampling-theorem bound, not an
  empirically tuned constant" where "not an X" already carries the
  contrast), cut it. Quantified claims ("genuine ~2x-or-more grid-size
  win," backed by concrete numbers immediately adjacent) are kept on
  the same logic as the real-vs-hypothetical category above.

Applying this test at the scale involved here (~2600 remaining
instances) means this file tracks *files to review*, not a mechanical
find-and-delete -- each file's checkbox means "read through and
resolved with judgment," not "word count reduced to zero."
