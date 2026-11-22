// Reads PDFs with Apple's built-in PDF reader (PDFKit), on this Mac only.
// Besides the text, it finds what people added ON the PDF: sticky notes,
// highlights (and the words under them), underlines, and handwriting drawn
// on the page. Scanned pages and handwriting are read with the Mac's own text
// reader (Vision). Nothing goes online and nothing is written to disk.
//
// Built by scripts/make-mac-app.sh:
//   swiftc -O scripts/pdf.swift -o bin/second-brain-pdf
// Usage:  bin/second-brain-pdf file.pdf

import AppKit
import Foundation
import PDFKit
import Vision

func readImage(_ image: NSImage) -> String {
    guard let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return "" }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([request])
    let found = request.results ?? []
    let sorted = found.sorted {
        let dy = $0.boundingBox.midY - $1.boundingBox.midY
        if abs(dy) > 0.02 { return dy > 0 }
        return $0.boundingBox.minX < $1.boundingBox.minX
    }
    return sorted.compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
}

let iso = ISO8601DateFormatter()
var results: [[String: Any]] = []

for path in CommandLine.arguments.dropFirst() {
    guard let doc = PDFDocument(url: URL(fileURLWithPath: path)) else {
        results.append(["path": path, "error": "could not open PDF"])
        continue
    }
    if doc.isLocked {
        results.append(["path": path, "error": "this PDF has a password"])
        continue
    }
    var pages: [[String: Any]] = []
    for i in 0..<min(doc.pageCount, 300) {
        guard let page = doc.page(at: i) else { continue }
        let text = page.string ?? ""
        var notes: [[String: Any]] = []
        var hasInk = false
        for a in page.annotations {
            let type = a.type ?? ""
            if type == "Popup" || type == "Link" || type == "Widget" { continue }
            var note: [String: Any] = ["type": type, "author": a.userName ?? "", "text": a.contents ?? ""]
            if let d = a.modificationDate { note["date"] = iso.string(from: d) }
            if ["Highlight", "Underline", "StrikeOut", "Squiggly"].contains(type) {
                note["marked"] = page.selection(for: a.bounds)?.string ?? ""
            }
            if type == "Ink" { hasInk = true }
            notes.append(note)
        }
        var page_: [String: Any] = ["text": text, "notes": notes]
        // Scanned page, or handwriting drawn on it: look at the page as a picture.
        if text.trimmingCharacters(in: .whitespacesAndNewlines).count < 20 || hasInk {
            let box = page.bounds(for: .mediaBox)
            let scale = 2000.0 / max(box.width, box.height)
            let image = page.thumbnail(of: NSSize(width: box.width * scale, height: box.height * scale), for: .mediaBox)
            let seen = readImage(image)
            if hasInk {
                // Only keep lines the typed text doesn't already contain: that is the handwriting.
                let typed = Set(text.lowercased().split(separator: "\n").map { $0.trimmingCharacters(in: .whitespaces) })
                page_["read_from_image"] = seen.split(separator: "\n").filter { !typed.contains($0.lowercased().trimmingCharacters(in: .whitespaces)) }.joined(separator: "\n")
            } else {
                page_["read_from_image"] = seen
            }
        }
        pages.append(page_)
    }
    results.append(["path": path, "pages": pages])
}

if let data = try? JSONSerialization.data(withJSONObject: results) {
    FileHandle.standardOutput.write(data)
}
