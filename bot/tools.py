"""Fayl konvertor va rasm tahrirlash (sof funksiyalar: bytes -> [(nom, bytes)])."""
import io
import fitz  # PyMuPDF
import docx
from PIL import Image, ImageOps


def _img(data):
    return ImageOps.exif_transpose(Image.open(io.BytesIO(data)))


def _save(im, fmt):
    buf = io.BytesIO()
    if fmt in ("JPEG", "PDF") and im.mode != "RGB":
        im = im.convert("RGB")
    im.save(buf, fmt)
    return buf.getvalue()


CONVERT_MODES = {
    "img2pdf": "🖼 Rasm → PDF", "img2jpg": "🖼 Rasm → JPG", "img2png": "🖼 Rasm → PNG",
    "img2webp": "🖼 Rasm → WEBP", "pdf2img": "📄 PDF → rasm", "pdf2txt": "📄 PDF → matn",
    "docx2txt": "📝 Word → matn", "txt2pdf": "📃 Matn fayl → PDF",
}


def convert(mode, data, name):
    base = name.rsplit(".", 1)[0] or "fayl"
    if mode == "img2pdf":
        return [(base + ".pdf", _save(_img(data), "PDF"))]
    if mode in ("img2jpg", "img2png", "img2webp"):
        fmt = {"img2jpg": "JPEG", "img2png": "PNG", "img2webp": "WEBP"}[mode]
        return [(f"{base}.{fmt.lower().replace('jpeg', 'jpg')}", _save(_img(data), fmt))]
    if mode == "pdf2img":
        doc = fitz.open(stream=data, filetype="pdf")
        return [(f"{base}_{i + 1}.png", p.get_pixmap(dpi=130).tobytes("png")) for i, p in enumerate(doc) if i < 10]
    if mode == "pdf2txt":
        doc = fitz.open(stream=data, filetype="pdf")
        return [(base + ".txt", "\n".join(p.get_text() for p in doc).encode())]
    if mode == "docx2txt":
        d = docx.Document(io.BytesIO(data))
        return [(base + ".txt", "\n".join(p.text for p in d.paragraphs).encode())]
    if mode == "txt2pdf":
        text = data.decode("utf-8", errors="ignore")
        doc = fitz.open()
        for i in range(0, max(len(text), 1), 2600):
            doc.new_page().insert_textbox(fitz.Rect(50, 50, 545, 790), text[i:i + 2600], fontsize=11)
        return [(base + ".pdf", doc.tobytes())]
    raise ValueError("Noma'lum rejim")


def crop(data, nums):
    """2 son: markazdan (kenglik, balandlik). 4 son: x, y, kenglik, balandlik (piksel)."""
    im = _img(data)
    W, H = im.size
    if len(nums) == 2:
        w, h = nums
        x, y = (W - w) // 2, (H - h) // 2
    elif len(nums) == 4:
        x, y, w, h = nums
    else:
        raise ValueError("2 yoki 4 ta son yuboring")
    box = (max(0, x), max(0, y), min(W, x + w), min(H, y + h))
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError(f"Qirqish maydoni rasm ichida emas. Rasm o'lchami: {W}x{H}")
    return [("crop.png", _save(im.crop(box), "PNG"))]


def split(data, n):
    cols, rows = {3: (3, 1), 4: (2, 2), 6: (3, 2)}[n]
    im = _img(data)
    W, H = im.size
    tw, th = W // cols, H // rows
    out = []
    for r in range(rows):
        for c in range(cols):
            out.append((f"part_{r * cols + c + 1}.png",
                        _save(im.crop((c * tw, r * th, (c + 1) * tw, (r + 1) * th)), "PNG")))
    return out
