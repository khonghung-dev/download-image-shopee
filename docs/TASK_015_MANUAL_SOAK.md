# Task 015 Manual Soak Checklist

Run this checklist on the same release candidate that passed the Task 015 automated suite. It intentionally uses real Shopee only at manual acceptance time. Do not change selectors, bypass verification/CAPTCHA, or begin packaging while collecting evidence.

## Before starting

- [ ] Confirm `pytest -ra` is green for the release candidate.
- [ ] Confirm Chrome Extension and Native Host are installed by the existing development procedure and the desktop shows a connected bridge.
- [ ] Choose a dedicated empty output root with enough free space. Record its absolute path.
- [ ] Enable the existing application logs and keep the terminal/Qt output visible.
- [ ] Record the current commit and `git status --short`.
- [ ] Prepare at least 30 valid Shopee product URLs. Do not store cookies, credentials, or tokens in this record.

## URL roster (30 minimum)

Fill one row per logical input. Prefer different shops, categories, gallery sizes, and title shapes. Include the required special cases in the Notes column.

| # | URL or private roster ID | Expected/observed `shop_id:item_id` | Gallery notes | Automatic authoritative images | Downloaded usable images | `product.json` count/length | Terminal state | Folder/notes |
|---:|---|---|---|---:|---:|---|---|---|
| 1 |  |  | Known 9 images + 1 video |  |  |  |  |  |
| 2 |  |  | Small gallery |  |  |  |  |  |
| 3 |  |  | Large gallery |  |  |  |  |  |
| 4 |  |  | Includes video if available |  |  |  |  |  |
| 5 |  |  | Vietnamese title |  |  |  |  |  |
| 6 |  |  | Long/emoji title if available |  |  |  |  |  |
| 7 |  |  | Different shop/category |  |  |  |  |  |
| 8 |  |  | Different gallery size |  |  |  |  |  |
| 9 |  |  | Different gallery size |  |  |  |  |  |
| 10 |  |  | Different gallery size |  |  |  |  |  |
| 11 |  |  | Different shop/category |  |  |  |  |  |
| 12 |  |  | Different shop/category |  |  |  |  |  |
| 13 |  |  | Different gallery size |  |  |  |  |  |
| 14 |  |  | Different gallery size |  |  |  |  |  |
| 15 |  |  | Different gallery size |  |  |  |  |  |
| 16 |  |  | Different shop/category |  |  |  |  |  |
| 17 |  |  | Different shop/category |  |  |  |  |  |
| 18 |  |  | Different gallery size |  |  |  |  |  |
| 19 |  |  | Different gallery size |  |  |  |  |  |
| 20 |  |  | Different gallery size |  |  |  |  |  |
| 21 |  |  | Different shop/category |  |  |  |  |  |
| 22 |  |  | Different shop/category |  |  |  |  |  |
| 23 |  |  | Different gallery size |  |  |  |  |  |
| 24 |  |  | Different gallery size |  |  |  |  |  |
| 25 |  |  | Different gallery size |  |  |  |  |  |
| 26 |  |  | Different shop/category |  |  |  |  |  |
| 27 |  |  | Different shop/category |  |  |  |  |  |
| 28 |  |  | Same product as an earlier row via a different accepted URL |  |  |  |  |  |
| 29 |  |  | Previously downloaded product |  |  |  |  |  |
| 30 |  |  | Different gallery size |  |  |  |  |  |

## Soak A — 30-product sequential batch

- [ ] Paste the 30+ URLs in the roster order and start one batch.
- [ ] Confirm only one logical product is opening/extracting/downloading at a time.
- [ ] Confirm the window remains movable/resizable and Cancel remains responsive during active downloads.
- [ ] Confirm each terminal row corresponds to the correct input/product. A legitimate Shopee/network failure is acceptable only when it becomes a controlled terminal state and later rows continue.
- [ ] Confirm final progress reaches the complete terminal count and the final summary accounts for every input.
- [ ] For every successful/partial item, verify the folder marker equals the observed `shop_id:item_id` and `product.json` parses as JSON.
- [ ] Confirm metadata `image_count` and `images` length equal the authoritative automatic extraction count.
- [ ] Confirm image files, marker, and metadata for each product are inside that product's folder only.
- [ ] Confirm no `.part`, marker-temp, or `product.json.tmp` remains after handled completion/failure.
- [ ] Confirm no crash, UI freeze, traceback, `QThread: Destroyed while thread is still running`, or cross-product folder/data leak appears.

Suggested read-only audits after the batch:

```powershell
Get-ChildItem -LiteralPath '<OUTPUT_ROOT>' -Recurse -File -Filter '*.part'
Get-ChildItem -LiteralPath '<OUTPUT_ROOT>' -Recurse -File -Filter 'product.json.tmp'
Get-ChildItem -LiteralPath '<OUTPUT_ROOT>' -Recurse -File -Filter '.shopee-product-id.*.tmp'
```

All three commands should return no files.

## Soak B — release-blocking known 9-image product

- [ ] Process the known product whose gallery has 9 images and 1 video through the automatic desktop batch.
- [ ] Record automatic authoritative images = 9.
- [ ] Record downloaded usable image files = 9.
- [ ] Parse `product.json`; record `image_count` = 9 and `images` length = 9.
- [ ] Open the same product in Chrome and use the existing manual Extension extraction. Record manual images = 9.
- [ ] If any count differs, stop. Capture URL/product identity, Extension debug/runtime output, current DOM evidence, and desktop logs before considering any extraction change.

## Soak C — duplicate and cross-run recovery

- [ ] Reprocess a completed marker-owned product from Soak A in a later batch.
- [ ] Confirm the same directory is reused, existing images remain intact/skipped, no duplicate folder appears, and metadata refreshes validly.
- [ ] Reprocess the same logical product through a different accepted URL when available.
- [ ] Confirm same-batch duplicate handling is terminal and does not start a second download/metadata pipeline.
- [ ] Create a recoverable partial state by using the normal cancellation/close scenario below; on rerun, confirm the same marker-owned folder is reused and only missing/invalid outputs are completed.
- [ ] Confirm an unmarked, malformed-marker, mismatched-marker, or multiple-claim directory is never silently adopted, merged, or overwritten.

## Soak D — cancel midway, then reuse the window

- [ ] Start a batch containing at least 20 valid URLs.
- [ ] Cancel approximately midway, preferably while an image is transferring.
- [ ] Wait for the clean terminal cancellation summary; do not force-kill the process.
- [ ] Confirm no later pending product starts after cancellation.
- [ ] Confirm completed final files remain and no `.part` remains.
- [ ] Without restarting the application, start a second small batch of different products.
- [ ] Confirm the second batch runs normally and receives no progress/result/error from the cancelled batch.

## Soak E — temporary network interruption

- [ ] Start a small batch of three to five products.
- [ ] Temporarily disconnect the network while a product is opening or downloading.
- [ ] Record the visible retry/error state and reconnect before the bounded policy is exhausted for one run.
- [ ] Confirm the current item either recovers on a valid current attempt or fails cleanly after the existing bound; later items continue.
- [ ] Confirm old/pre-reconnect results cannot complete the newer request generation.
- [ ] If Shopee requests verification, complete it manually in Chrome and use Continue. Confirm no automatic attempt is consumed while paused.
- [ ] Do not bypass verification/CAPTCHA.

## Soak F — normal close during active download and recovery

- [ ] Start a product with enough images to observe an active transfer.
- [ ] Close the application normally during the download.
- [ ] Confirm the process exits within a reasonable bounded time without force termination.
- [ ] Confirm no visible Qt thread-destroyed error, corrupt final image, corrupt `product.json`, or orphan temp file remains.
- [ ] Reopen the application and process the same product again.
- [ ] Confirm its marker-owned folder is reused, completed images are preserved, missing images finish, and final metadata is valid.

## Sign-off

- [ ] 30+ product soak completed.
- [ ] Known automatic 9-image count = 9.
- [ ] Known manual Extension count = 9.
- [ ] Cancel → second batch completed without stale callbacks.
- [ ] Network interruption handled within current policy.
- [ ] Normal close/reopen recovered through existing-folder logic.
- [ ] No release-blocking condition from Task 015 remains reproducible.

Record tester, date/time, commit, Windows version, Chrome/Extension version, output root, final summary, and links/paths to logs. If any release-blocker fails, mark Task 015 not ready and attach the exact reproduction evidence; do not begin Task 016.
