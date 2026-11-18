"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
REMOVE_CODES = {"DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}


def _fmt(v):
    return f"{v:.6f}".rstrip("0").rstrip(".") or "0"


def _clip(cid, cx, cy, w, h):
    """Cắt box về [0,1]; trả về None nếu sau khi cắt không còn diện tích."""
    x1, x2 = max(0.0, cx - w / 2), min(1.0, cx + w / 2)
    y1, y2 = max(0.0, cy - h / 2), min(1.0, cy + h / 2)
    if x2 - x1 <= 0 or y2 - y1 <= 0:
        return None
    return f"{cid} {_fmt((x1 + x2) / 2)} {_fmt((y1 + y2) / 2)} {_fmt(x2 - x1)} {_fmt(y2 - y1)}"


def fix(ds, issues, cfg):
    fixes = []
    errors = [i for i in issues if i.severity == ERROR]            # cảnh báo là việc của người, không đụng tới

    # 1) xoá ảnh trước; mọi issue còn lại của ảnh đã xoá bị bỏ qua êm
    removed = set()
    for i in sorted((i for i in errors if i.code in REMOVE_CODES), key=lambda i: i.image):
        if i.image in removed:
            continue
        removed.add(i.image)
        gone = []
        for p in ds.images_dir.glob(i.image + ".*") if ds.images_dir.exists() else []:
            if p.stem == i.image:
                p.unlink()
                gone.append(p.name)
        lp = ds.label_path(i.image)
        if lp.exists():
            lp.unlink()
        fixes.append(dict(image=i.image, line=None, action="remove_image", before=f"{i.code}: " + (", ".join(gone) or i.image), after="(đã xoá ảnh + nhãn)"))

    # 2) lỗi theo dòng: gom theo file, ghi lại MỘT lần, dùng số dòng gốc
    per_file = defaultdict(lambda: defaultdict(set))                 # stem -> line -> {code}
    for i in errors:
        if i.image in removed or i.line is None:
            continue
        if i.code in DROP_CODES or i.code == "BOX_OUT_OF_IMAGE":
            per_file[i.image][i.line].add(i.code)
    for stem in sorted(per_file):
        lp = ds.label_path(stem)
        if not lp.exists():
            continue
        raw_lines = lp.read_text(encoding="utf-8", errors="replace").splitlines()
        out = list(raw_lines)
        drop = set()
        for ln in sorted(per_file[stem]):
            if not 1 <= ln <= len(raw_lines):
                continue
            codes = per_file[stem][ln]
            text = raw_lines[ln - 1]
            if codes & DROP_CODES:                                   # dòng thắng: xoá, không clip thêm
                drop.add(ln)
                fixes.append(dict(image=stem, line=ln, action="drop_line", before=text, after="(đã xoá dòng)"))
                continue
            try:
                new = _clip(*parse_yolo_line(text))
            except ValueError:
                new = None
            if new is None:
                drop.add(ln)
                fixes.append(dict(image=stem, line=ln, action="drop_line", before=text, after="(đã xoá dòng: box nằm ngoài ảnh)"))
            else:
                out[ln - 1] = new
                fixes.append(dict(image=stem, line=ln, action="clip_box", before=text, after=new))
        keep = [t for k, t in enumerate(out, 1) if k not in drop]
        with open(lp, "w", encoding="utf-8", newline="\n") as f:
            f.write("".join(t + "\n" for t in keep))

    # 3) ảnh chưa có nhãn: máy không bịa nhãn
    for stem in sorted({i.image for i in errors if i.code == "MISSING_LABEL_FILE" and i.image not in removed}):
        fixes.append(dict(image=stem, line=None, action="needs_label", before="(không có file)", after="chuyển người gán"))

    # 4) tên lớp trong data.yaml
    if any(i.code == "BAD_CLASS_NAME" for i in errors) and ds.yaml_path.exists():
        d = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
        before = d.get("names")
        d["names"] = {k: n for k, n in enumerate(cfg["classes"])}
        with open(ds.yaml_path, "w", encoding="utf-8", newline="\n") as f:
            yaml.safe_dump(d, f, allow_unicode=True, sort_keys=False)
        fixes.append(dict(image="data.yaml", line=None, action="rename_classes", before=str(before), after=str(list(cfg["classes"]))))
    return fixes

