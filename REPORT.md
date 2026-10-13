# REPORT — Lab Day 9

> Điền **bằng lời và số liệu của chính bạn** (lấy từ đầu ra của `scripts/lab.sh step ...` và từ `report/evidence/*.json`). Bài làm công khai trên GitHub; giảng viên đối chiếu với lịch sử commit và với bài của các bạn khác. Mỗi câu 3 đến 8 dòng là đủ.

| | |
|---|---|
| Họ và tên | Nguyen Thanh Hoa |
| MSSV (đúng bằng `LAB_STUDENT_ID` trong `.env`) | `2A202602559` |
| GitHub | `Jikay-070203` |
| Trip dùng cho bài tập sập và chạy lại (xem GUIDE, bước 5) | `trip-00003` |

## Kết quả cuối

- `dataset_version` của bạn: `15d3ffecad45` (phải khớp `report/evidence/run_summary.json`)
- Số khung hình train / val / test của bạn: `701 / 186 / 132`
- `report/verify.txt`: tạo bằng `python3 scripts/check_submission.py --save-verify` (phải có `27/27 checks passed`).
- Ảnh chụp trong `report/screenshots/`: `airflow_graph.png`, `minio_lake.png`, `metabase_dashboard.png`, và ảnh bài tập sập/chạy lại (log task đỏ thấy trip của bạn).

## Bước 1 · Bronze

### Câu 1
Liệt kê **ít nhất 4 khác biệt** giữa telemetry nguồn A và nguồn B mà bạn thấy ở bronze. Vì sao pipeline giữ **mỗi nguồn một bảng bronze** và để mọi cột ở dạng chữ, thay vì gộp và ép kiểu ngay?

Telemetry A dùng các cột ts_utc, speed_mps, heading_deg, lat, lon, alt_m, acc_x, acc_y, gas, brake, steer; telemetry B dùng timestamp_ms, spd_kmh, hdg, latitude, longitude, altitude, ax, ay, throttle_pct, brake_pct, steering. A dùng timestamp ISO UTC còn B dùng epoch milliseconds. Tốc độ A là m/s còn B là km/h. Tên và đơn vị của gia tốc, bàn đạp ga/phanh và góc lái cũng khác nhau. Pipeline giữ hai bảng Bronze riêng để bảo toàn dữ liệu nguyên bản và tránh mất thông tin khi schema thay đổi. Các cột để dạng chữ nhằm trì hoãn ép kiểu; việc chuẩn hóa và kiểm tra lỗi được thực hiện ở Silver, nơi có thể đưa dòng lỗi vào quarantine thay vì làm hỏng toàn bộ dữ liệu.

## Bước 2 · Silver telemetry

### Câu 2
Pipeline đưa hai nguồn về một schema như thế nào (đơn vị, kiểu thời gian, **độ lệch đồng hồ**)? Bằng chứng nào trong kết quả bước 2 cho thấy đã đúng? Dán bảng quarantine của bạn (số dòng theo từng lý do, từng drive) và giải thích vì sao dòng lỗi vào `rejects` thay vì bị xoá.

Pipeline chuẩn hóa hai nguồn tại Silver bằng cách đổi tên cột về schema chung, chuyển tốc độ của nguồn B từ km/h sang m/s, chuyển timestamp epoch milliseconds về timestamp UTC, đồng thời trừ độ lệch đồng hồ 1500 ms của drive_b. Bằng chứng là dữ liệu B được đưa về các cột chung như ts, speed_mps, heading_deg và thời gian bắt đầu khớp với video sau khi hiệu chỉnh.  
Bảng quarantine ghi nhận:
| Drive | Duplicate | Speed missing | Speed out of range |
|---|---:|---:|---:|
| drive_a | 20 | 30 | 3 |
| drive_b | 20 | 30 | 3 |

### Câu 3
Vì sao test `max_gap_ms` là `warn` còn `in_range` là `error`? Kết quả thí nghiệm `break-gate` của bạn (`break_gate.json`): test nào bắt được, bao nhiêu dòng, và điều đó cho biết gì về vai trò của "cổng chất lượng"?

max_gap_ms đặt ở mức warn vì mất tín hiệu cảm biến là vấn đề cần theo dõi nhưng chưa chắc làm dữ liệu không sử dụng được. Ngược lại, in_range đặt ở mức error vì tốc độ ngoài khoảng hợp lệ có thể làm sai kết quả phân tích và huấn luyện. Trong thí nghiệm break-gate, khi nới ngưỡng tốc độ tối đa lên 1000 m/s, test in_range_silver_telemetry_speed_mps__70__0 đã phát hiện 6 dòng lỗi. Khi khôi phục ngưỡng ban đầu, kết quả trở lại PASS=6, WARN=1, ERROR=0. Điều này cho thấy quality gate có thể chặn dữ liệu nghiêm trọng trước khi đi tiếp, trong khi các cảnh báo ít nghiêm trọng hơn vẫn cho phép pipeline tiếp tục.

## Bước 3 · Silver frames

### Câu 4
Dựa vào `idempotency.json`: số dòng trước và sau hai lần chạy lại, và khi ghi kiểu `append`. Vì sao Delta `overwrite` theo partition (một trip) an toàn hơn xoá rồi ghi lại, nhất là khi giữa chừng có lỗi?

Với trip-00003, bảng có 1246 dòng trước khi chạy lại và vẫn có 1246 dòng sau hai lần chạy lại. Fingerprint trước và sau đều là 6c7480dfde7e, chứng minh pipeline idempotent. Khi dùng cách ghi append sai, partition của trip có 60 dòng nhưng sau hai lần ghi đã thành 120 dòng, tức dữ liệu bị nhân đôi. Delta overwrite theo partition an toàn hơn xóa rồi ghi lại vì chỉ thay thế đúng partition của một trip trong một giao dịch. Nếu job lỗi giữa chừng, các partition khác không bị ảnh hưởng và có thể chạy lại partition đó mà không tạo bản ghi trùng.

### Câu 5
Khung hình **đen** và khung hình **tối** khác nhau thế nào, pipeline xử lý khác nhau ra sao, bạn có đồng ý không? Dựa vào `threshold.json`: nếu chọn ngưỡng 0, 2, 6 thì bao nhiêu khung bị coi là trùng ở mỗi drive? Bạn chọn ngưỡng nào, vì sao, và ngưỡng đó phụ thuộc vào tốc độ xe thế nào?

| dHash khác tối đa | số khung trùng, drive A | số khung trùng, drive B |
|---|---|---|
| 0 | | |
| 2 | | |
| 6 | | |

| Ngưỡng dHash | Drive A | Drive B |
|---:|---:|---:|
| 0 bit | 61 | 8 |
| 2 bit | 149 | 53 |
| 6 bit | 363 | 244 |

Pipeline đang dùng ngưỡng 2 bit.

Frame đen là frame gần như không có tín hiệu hình ảnh, thường do lỗi video hoặc màn hình hoàn toàn đen; pipeline đánh dấu là đen và không giữ lại để huấn luyện. Frame tối vẫn còn nội dung hình ảnh, chẳng hạn đường hầm hoặc bóng râm, nên được đánh dấu chất lượng thấp nhưng vẫn giữ lại. Ở ngưỡng dHash 0, có 61 frame trùng ở drive A và 8 ở drive B; ngưỡng 2 lần lượt là 149 và 53; ngưỡng 6 lần lượt là 363 và 244. Tôi chọn ngưỡng 2 vì loại được các frame gần như giống hệt nhưng không loại quá nhiều frame chỉ khác nhẹ do chuyển động hoặc nhiễu. Xe chạy càng chậm thì các frame liên tiếp càng giống nhau, nên có thể cần ngưỡng chặt hơn; xe chạy nhanh tạo khác biệt lớn hơn giữa các frame.


## Bước 4 · Gold

### Câu 6
Dựa vào `leakage.json`: chia theo khung hình làm bao nhiêu trip bị chia cắt, so với chia theo trip? Vì sao điều này làm điểm kiểm thử đẹp một cách giả tạo?

Khi chia ngẫu nhiên theo frame, cả 26 trip đều bị chia vào nhiều split và đều có frame xuất hiện ở cả train lẫn test. Ngược lại, cách chia theo trip của pipeline có 0 trip bị chia cắt. Các frame liền nhau trong cùng một chuyến thường rất giống nhau, nên nếu một số frame vào train và các frame gần kề vào test thì mô hình gần như đã nhìn thấy dữ liệu kiểm thử. Vì vậy điểm test sẽ cao một cách giả tạo và không phản ánh khả năng tổng quát hóa sang chuyến xe mới.

### Câu 7
Vì sao `dataset_version` là **băm nội dung** chứ không phải ngày giờ hay số đếm? Hai lần chạy liên tiếp cho kết quả gì? Vì sao `dataset_version` của bạn **khác** bạn bè dù cùng dữ liệu (liên hệ MSSV)?

dataset_version là mã băm nội dung được tạo từ danh sách frame và split, nên cùng một dữ liệu và cùng cách chia sẽ tạo ra cùng một version dù chạy ở thời điểm khác nhau. Dataset của tôi có version 15d3ffecad45. MSSV được dùng trong quá trình chia trip vào các split; nếu đổi MSSV, cách chia có thể thay đổi, từ đó danh sách frame/split và dataset_version cũng thay đổi.

### Câu 8
Đọc phần `lineage` trong `manifest.json` của dataset bạn. Trả lời "dataset này được tạo từ dữ liệu nào?" bằng chính nội dung đó. Nếu một người hỏi 3 tháng sau, thông tin nào giúp tái tạo lại đúng dataset này?

Dataset được tạo từ các bảng Bronze gồm raw_telemetry_a version 0, raw_telemetry_b version 0, trips_raw version 0 và video_files version 1. Các bảng Silver đầu vào là frames version 27, telemetry version 1, frames_flagged version 0 và frame_telemetry version 0. Dataset chứa 1019 frame, loại các frame đen, mờ, trùng gần, hoặc không đồng bộ. Manifest cũng lưu SHA256 của hai video đầu vào, giúp tái tạo đúng dataset sau này và phát hiện nếu video nguồn bị thay đổi.

## Bước 5 · Điều phối và phục vụ

### Câu 9
Mô tả chính xác điều xảy ra khi trip của bạn sập rồi chạy lại: bao nhiêu task chuyển đỏ, bao nhiêu task `upstream_failed`, bạn clear gì, dữ liệu có nhân đôi không, `dataset_version` có đổi không? Bằng chứng (ảnh, số) là gì?

Trong bài tập retry, task `silver_frames` của `trip-00003` chuyển đỏ với log `simulated crash while extracting trip-00003`; các task phụ thuộc chuyển `upstream_failed`. Tôi chỉ clear task đỏ rồi chạy lại, sau đó DAG xanh hoàn toàn. Bằng chứng là `airflow_failed_task.png` và `airflow_retry_success.png`. Verify vẫn đạt 27/27, dataset version vẫn `15d3ffecad45`, số frame không đổi và dữ liệu không bị nhân đôi nhờ ghi idempotent theo partition.

### Câu 10
Nâng từ 2 drive lên **500 xe mỗi ngày**: ba thành phần nào của pipeline này sẽ vỡ đầu tiên, và bạn thay bằng gì (nối với slide 12, 22, 23)?

Khi tăng từ 2 drive lên 500 xe mỗi ngày, ba điểm dễ quá tải trước là decode video/FFmpeg, object storage và tài nguyên điều phối cùng warehouse. Nên thay xử lý tuần tự bằng worker phân tán và hàng đợi, mở rộng object storage theo chiều ngang và dùng multipart upload. Airflow cần thêm worker, còn Postgres/warehouse cần partitioning, indexing hoặc hệ thống OLAP phù hợp. Retry và giám sát chất lượng cũng phải được giới hạn để một xe lỗi không chặn toàn bộ ngày xử lý.

## Câu hỏi riêng của bạn trên Metabase

Câu SQL bạn thêm vào dashboard và điều nó cho biết:

SQL đã thêm trên dashboard là `select drive_id, rows_duplicate, rows_speed_missing, rows_speed_out_of_range from marts.mart_telemetry_quality order by drive_id`. Câu hỏi này cho biết số dòng telemetry bị quarantine theo từng drive và từng nguyên nhân, giúp so sánh chất lượng dữ liệu giữa hai nguồn. Kết quả phù hợp với số liệu Silver: mỗi drive có 20 duplicate, 30 speed missing và 3 speed out of range.

## Nhìn lại

Điều bạn thấy bất ngờ nhất, điều gì còn chưa rõ, và một lỗi dữ liệu mà bạn nghĩ pipeline **chưa** bắt được (nếu có). Tối đa 8 dòng.

Điều bất ngờ nhất là chia theo frame làm cả 26 trip bị rò rỉ sang train và test dù số frame vẫn hợp lệ. Việc giữ dòng lỗi trong quarantine giúp kiểm tra đầy đủ thay vì che giấu vấn đề. Pipeline đã bắt được duplicate, thiếu tốc độ, tốc độ bất thường, frame đen, mờ và lệch đồng bộ. Một lỗi có thể chưa bắt được là giá trị cảm biến hợp lệ về miền số nhưng sai về ngữ nghĩa hoặc sai vị trí địa lý; trường hợp đó cần thêm kiểm tra liên trường và bản đồ.
