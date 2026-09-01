"""Task 014 presentation and reusable-window UI regressions."""

from __future__ import annotations

from pathlib import Path

from shopee_image_downloader.core.batch_queue import ItemState, QueueState
from shopee_image_downloader.core.image_downloader import (
    ImageDownloadResult,
    ImageDownloadStatus,
    ProductDownloadResult,
)
from tests.test_ui import (
    HoldingImageDownloadController,
    ImmediateImageDownloadController,
    _create_window,
    _product,
)


def _partial_result(product, successful: int) -> ProductDownloadResult:
    items: list[ImageDownloadResult] = []
    assert product.product_folder is not None
    for index, source_url in enumerate(product.images, start=1):
        status = (
            ImageDownloadStatus.SUCCESS
            if index <= successful
            else ImageDownloadStatus.FAILED
        )
        items.append(
            ImageDownloadResult(
                index=index,
                source_url=source_url,
                target_path=product.product_folder / f"{index:02d}.jpg",
                status=status,
                attempts=1,
                error=None if status == ImageDownloadStatus.SUCCESS else "HTTP 404",
            )
        )
    return ProductDownloadResult.from_items(len(product.images), items)


def test_initial_ui_state_is_clear_and_idle(tmp_path: Path) -> None:
    window, _, _ = _create_window(tmp_path)

    assert window.start_button.isEnabled()
    assert not window.cancel_button.isEnabled()
    assert window.url_input.isEnabled()
    assert window.output_folder_input.isEnabled()
    assert window.select_folder_button.isEnabled()
    assert not window.export_metadata_checkbox.isChecked()
    assert not window.export_marker_checkbox.isChecked()
    assert window.export_metadata_checkbox.isEnabled()
    assert window.export_marker_checkbox.isEnabled()
    assert window.progress_bar.value() == 0
    assert not window.progress_bar.isTextVisible()
    assert window.progress_percent_label.text() == "0%"
    assert window.batch_progress_label.text() == "Sản phẩm 0/0"
    assert window.current_product_label.text() == "Chưa bắt đầu xử lý."
    assert window.status_label.text() == "Chưa có sản phẩm nào được xử lý."
    window.close()


def test_percentage_is_rendered_to_the_right_of_progress_bar(
    tmp_path: Path,
    qtbot,
) -> None:
    window, _, _ = _create_window(tmp_path)
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(10)

    for value in (0, 40, 100):
        window.progress_bar.setValue(value)
        assert window.progress_percent_label.text() == f"{value}%"
    assert not window.progress_bar.isTextVisible()
    assert window.progress_percent_label.geometry().left() >= (
        window.progress_bar.geometry().right()
    )
    window.close()


def test_default_layout_gives_url_grid_the_requested_larger_height(
    tmp_path: Path,
    qtbot,
) -> None:
    window, _, _ = _create_window(tmp_path)
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(10)

    # The former editor's default minimum was 82 px. The redesigned default
    # keeps roughly 2.5 times that space while the window remains resizable.
    assert window.url_input.height() >= 180
    assert window.content_splitter.sizes()[0] > (
        window.content_splitter.sizes()[1]
    )
    window.close()


def test_valid_url_count_reuses_parser_deduplication(tmp_path: Path) -> None:
    window, _, _ = _create_window(tmp_path)

    window.url_input.setPlainText(
        "\nhttps://shopee.vn/a\nhttps://shopee.vn/a\n"
        "https://s.shopee.vn/b\nhttps://example.com/not-shopee\n"
    )

    assert window.url_count_label.text() == "2 link hợp lệ"
    window.close()


def test_running_state_locks_inputs_and_shows_overall_progress(
    tmp_path: Path,
) -> None:
    window, _, _ = _create_window(
        tmp_path,
        connected=True,
        with_output_folder=True,
    )
    window.url_input.setPlainText("https://shopee.vn/product-1")

    window.start_button.click()

    assert window.queue_manager.state == QueueState.RUNNING
    assert not window.start_button.isEnabled()
    assert window.cancel_button.isEnabled()
    assert not window.url_input.isEnabled()
    assert not window.output_folder_input.isEnabled()
    assert not window.select_folder_button.isEnabled()
    assert not window.export_metadata_checkbox.isEnabled()
    assert not window.export_marker_checkbox.isEnabled()
    assert window.batch_progress_label.text() == "Sản phẩm 0/1"
    assert window.current_product_label.text() == (
        "Sản phẩm 1/1 — Đang mở sản phẩm"
    )
    window.cancel_button.click()
    window.close()


def test_pause_button_waits_for_extraction_boundary_and_resumes_once(
    tmp_path: Path,
) -> None:
    controller = ImmediateImageDownloadController()
    window, _, _ = _create_window(
        tmp_path,
        connected=True,
        with_output_folder=True,
        image_download_controller=controller,
    )
    window.url_input.setPlainText("https://shopee.vn/product-pause")
    window.start_button.click()
    request_id = window.queue_manager.current_item.request_id

    assert window.pause_button.text() == "Tạm dừng"
    assert window.pause_button.isEnabled()
    window.pause_button.click()

    assert window.queue_manager.state == QueueState.PAUSE_REQUESTED
    assert window.pause_button.text() == "Đang tạm dừng..."
    assert not window.pause_button.isEnabled()

    window._on_bridge_product_received(_product(request_id=request_id))

    assert window.queue_manager.state == QueueState.PAUSED_USER
    assert window.pause_button.text() == "Tiếp tục"
    assert window.pause_button.isEnabled()
    assert controller.start_calls == []

    window.pause_button.click()

    assert window.queue_manager.state == QueueState.IDLE
    assert controller.start_calls == ["1001:2001"]
    assert window.pause_button.text() == "Tạm dừng"
    assert not window.pause_button.isEnabled()
    assert window.start_button.isEnabled()
    window.close()


def test_finished_and_second_batch_restore_reusable_state(tmp_path: Path) -> None:
    window, _, _ = _create_window(
        tmp_path,
        connected=True,
        with_output_folder=True,
        image_download_controller=ImmediateImageDownloadController(),
    )

    window.url_input.setPlainText("https://shopee.vn/product-a")
    window.start_button.click()
    first_request = window.queue_manager.current_item.request_id
    window._on_bridge_product_received(
        _product(request_id=first_request, item_id="2001", image_count=2)
    )

    assert window.queue_manager.state == QueueState.IDLE
    assert window.start_button.isEnabled()
    assert not window.cancel_button.isEnabled()
    assert window.url_input.isEnabled()
    assert window.output_folder_input.isEnabled()
    assert window.status_label.text() == "Hoàn tất 1/1 sản phẩm."

    window.url_input.setPlainText("https://shopee.vn/product-b")
    window.start_button.click()
    second_request = window.queue_manager.current_item.request_id
    window._on_bridge_product_received(
        _product(
            request_id=second_request,
            shop_id="1002",
            item_id="2002",
            image_count=1,
        )
    )

    assert window.queue_manager.state == QueueState.IDLE
    assert window.results_table.rowCount() == 1
    assert window.results_table.item(0, window.COL_IMAGES).text() == "1/1"
    assert "1002:2002" in window._products_by_product_key
    assert "1001:2001" not in window._products_by_product_key
    assert window.start_button.isEnabled()
    window.close()


def test_cancelled_state_is_terminal_and_cancel_is_single_shot(
    tmp_path: Path,
) -> None:
    controller = HoldingImageDownloadController()
    window, _, _ = _create_window(
        tmp_path,
        connected=True,
        with_output_folder=True,
        image_download_controller=controller,
    )
    window.url_input.setPlainText(
        "https://shopee.vn/product-1\nhttps://shopee.vn/product-2"
    )
    window.start_button.click()
    request_id = window.queue_manager.current_item.request_id
    window._on_bridge_product_received(
        _product(request_id=request_id, image_count=2)
    )

    window.cancel_button.click()
    window.cancel_button.click()

    assert controller.cancel_calls == 1
    assert window.queue_manager.state == QueueState.IDLE
    assert window.start_button.isEnabled()
    assert not window.cancel_button.isEnabled()
    assert "Đang tải" not in window.current_product_label.text()
    assert "hủy" in window.current_product_label.text().lower()
    assert window.status_label.text().startswith("Đã hủy")
    window.close()


def test_retry_uses_friendly_attempt_text_without_new_row(tmp_path: Path) -> None:
    window, _, _ = _create_window(
        tmp_path,
        connected=True,
        with_output_folder=True,
    )
    window.url_input.setPlainText("https://shopee.vn/product-retry")
    window.start_button.click()
    first_request = window.queue_manager.current_item.request_id

    window._on_bridge_process_error_received(
        first_request,
        "https://shopee.vn/product-retry",
        "PRODUCT_TIMEOUT",
        "timeout",
    )

    assert window.queue_manager.current_item.state == ItemState.WAITING_RETRY
    assert window.results_table.rowCount() == 1
    assert window.results_table.item(0, window.COL_STATUS).text() == (
        "Đang thử lại 2/3..."
    )

    window.queue_manager._retry_timer.stop()
    window.queue_manager._on_retry_timeout()
    second_request = window.queue_manager.current_item.request_id
    assert second_request != first_request
    assert window.results_table.rowCount() == 1
    assert window._rows_by_request_id[first_request] == 0
    assert window._rows_by_request_id[second_request] == 0

    window._on_bridge_product_received(_product(request_id=second_request))
    assert window.results_table.rowCount() == 1
    window.close()


def test_image_progress_metadata_and_partial_result_are_not_overstated(
    tmp_path: Path,
) -> None:
    controller = HoldingImageDownloadController()
    window, _, _ = _create_window(
        tmp_path,
        connected=True,
        with_output_folder=True,
        image_download_controller=controller,
    )
    source_product = _product(image_count=9)
    original_images = list(source_product.images)
    window.url_input.setPlainText("https://shopee.vn/product-partial")
    window.start_button.click()
    request_id = window.queue_manager.current_item.request_id
    source_product = _product(request_id=request_id, image_count=9)
    window._on_bridge_product_received(source_product)
    active = controller.active_product
    assert active is not None

    controller.progress.emit(active, 5, 9)
    assert window.results_table.item(0, window.COL_IMAGES).text() == "5/9"
    assert "Đang tải ảnh 5/9" in window.current_product_label.text()

    window._on_metadata_started(active)
    assert window.results_table.item(0, window.COL_STATUS).text() == (
        "Đang lưu thông tin sản phẩm..."
    )

    result = _partial_result(active, successful=8)
    controller.active_product = None
    controller.finished.emit(active, result)
    controller.idle.emit()

    stored = window._products_by_product_key[source_product.product_key]
    assert len(source_product.images) == 9
    assert source_product.images == original_images
    assert len(stored.images) == 9
    assert window.results_table.item(0, window.COL_IMAGES).text() == "8/9"
    assert window.results_table.item(0, window.COL_STATUS).text() == (
        "Hoàn tất một phần — 8/9 ảnh"
    )
    assert "9/9" not in window.results_table.item(0, window.COL_STATUS).text()
    window.close()


def test_duplicate_is_handled_not_failed(tmp_path: Path) -> None:
    controller = ImmediateImageDownloadController()
    window, _, _ = _create_window(
        tmp_path,
        connected=True,
        with_output_folder=True,
        image_download_controller=controller,
    )
    window.url_input.setPlainText(
        "https://shopee.vn/product-a\nhttps://s.shopee.vn/product-a"
    )
    window.start_button.click()
    first_request = window.queue_manager.current_item.request_id
    window._on_bridge_product_received(_product(request_id=first_request))
    second_request = window.queue_manager.current_item.request_id
    window._on_bridge_product_received(_product(request_id=second_request))

    assert window.queue_manager.items[1].state == ItemState.SKIPPED_DUPLICATE
    status = window.results_table.item(1, window.COL_STATUS).text()
    assert status == "Trùng sản phẩm — đã bỏ qua"
    assert "Lỗi" not in status
    window.close()


def test_long_product_and_output_path_preserve_full_values(
    tmp_path: Path,
    qtbot,
) -> None:
    long_output = tmp_path
    for index in range(3):
        long_output = long_output / (f"thu-muc-luu-anh-{index}-" + "x" * 20)
    long_output.mkdir(parents=True)
    long_name = "Sản phẩm tên rất dài " + "đầy đủ " * 35

    window, _, _ = _create_window(
        tmp_path,
        with_output_folder=True,
        image_download_controller=ImmediateImageDownloadController(),
    )
    qtbot.addWidget(window)
    window.resize(620, 480)
    window.show()
    window.output_folder_input.setText(str(long_output))
    window._on_bridge_product_received(
        _product(name=long_name, image_count=1)
    )
    qtbot.wait(10)

    product_item = window.results_table.item(0, window.COL_PRODUCT)
    assert window.output_folder_input.text() == str(long_output)
    assert window.output_folder_input.toolTip() == str(long_output)
    assert product_item.text() == long_name
    assert long_name in product_item.toolTip()
    assert window.output_folder_input.width() < (
        window.output_folder_input.fontMetrics().horizontalAdvance(str(long_output))
    )
    assert window.results_table.columnWidth(window.COL_PRODUCT) < (
        window.results_table.fontMetrics().horizontalAdvance(long_name)
    )
    window.close()


def test_default_smaller_and_larger_window_layouts_keep_controls_usable(
    tmp_path: Path,
    qtbot,
) -> None:
    window, _, _ = _create_window(tmp_path, with_output_folder=True)
    qtbot.addWidget(window)
    window.show()

    for width, height in ((850, 650), (620, 480), (1200, 800)):
        window.resize(width, height)
        qtbot.wait(10)
        central_rect = window.centralWidget().rect()
        for widget in (
            window.url_input,
            window.output_folder_input,
            window.select_folder_button,
            window.start_button,
            window.cancel_button,
            window.progress_bar,
            window.results_table,
            window.status_label,
        ):
            top_left = widget.mapTo(window.centralWidget(), widget.rect().topLeft())
            bottom_right = widget.mapTo(
                window.centralWidget(),
                widget.rect().bottomRight(),
            )
            assert central_rect.contains(top_left)
            assert central_rect.contains(bottom_right)
            assert widget.width() > 0
            assert widget.height() > 0

        assert window.url_input.height() >= window.url_input.minimumHeight()
        assert window.results_table.height() >= window.results_table.minimumHeight()

    window.close()
