# Project Context: Shopee Image Downloader

## Product Overview

**Shopee Image Downloader** is a specialized Windows desktop tool tailored for e-commerce sellers, catalog managers, and researchers who need to download high-resolution product images in bulk from Shopee listings.

## Key Requirements & Capabilities

1. **Multi-link Batch Input**:
   - Accepts a list of Shopee product URLs provided by the user (one link per line).
   - Supports different Shopee URL formats (e.g., standard web URLs, shortlinks, mobile sharing URLs).

2. **Destination Folder Selection**:
   - Allows the user to select a root download directory via a native Windows directory picker dialog.
   - Persists user preferences (e.g., last used directory) where appropriate.

3. **Metadata & Image Extraction**:
   - Parses Shopee links to identify item ID, shop ID, and product name.
   - Extracts all associated media: main cover photos, gallery images, variation/tier model photos, and description images.
   - Selects the highest available image resolution.

4. **Organized Output Structure**:
   - Creates a dedicated subfolder for each product inside the selected root directory.
   - Subfolder naming follows a clean, Windows-safe convention (e.g., `<item_id>_<sanitized_product_name>`).
   - Image files are saved with sequential numbering and proper extensions (`01_cover.jpg`, `02_gallery_1.jpg`, etc.).

5. **Fault Tolerance & Error Recovery**:
   - If an individual product link is invalid, geo-blocked, deleted, or encounters a network error, the application records a clear failure status for that item and immediately continues processing the rest of the queue.
   - Produces a summary report (e.g., X succeeded, Y failed) upon batch completion.

6. **Responsive User Interface**:
   - The desktop GUI remains completely interactive at all times.
   - Real-time progress indicators (item progress, overall queue progress, log viewer) update smoothly via Qt signals.
   - Supports cancellation / pausing if requested by the user.
