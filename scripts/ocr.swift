// Reads the text in screenshots and photos using Apple's on-device Vision
// framework (the same text reader the Photos app uses). Nothing goes online.
// It writes nothing to disk: results are printed for Codicilix to read.
//
// For each image it returns the text, plus where every word sits on the
// picture, so Codicilix can let you select and highlight words on the photo.
//
// Built once by scripts/make-mac-app.sh:
//   swiftc -O scripts/ocr.swift -o bin/second-brain-ocr
// Usage:
//   bin/second-brain-ocr image1.png image2.jpg ...
//   bin/second-brain-ocr -          (reads one image from standard input)

import AppKit
import Foundation
import Vision

func loadImage(_ arg: String) -> CGImage? {
    let image: NSImage?
    if arg == "-" {
        image = NSImage(data: FileHandle.standardInput.readDataToEndOfFile())
    } else {
        image = NSImage(contentsOf: URL(fileURLWithPath: arg))
    }
    return image?.cgImage(forProposedRect: nil, context: nil, hints: nil)
}

var results: [[String: Any]] = []

for path in CommandLine.arguments.dropFirst() {
    guard let cg = loadImage(path) else {
        results.append(["path": path, "text": "", "error": "could not open image"])
        continue
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do {
        try handler.perform([request])
    } catch {
        results.append(["path": path, "text": "", "error": "\(error)"])
        continue
    }
    let observations = request.results ?? []
    // Top of the image first, then left to right.
    let sorted = observations.sorted {
        let dy = $0.boundingBox.midY - $1.boundingBox.midY
        if abs(dy) > 0.02 { return dy > 0 }
        return $0.boundingBox.minX < $1.boundingBox.minX
    }
    var lines: [String] = []
    var words: [[String: Any]] = []
    for observation in sorted {
        guard let candidate = observation.topCandidates(1).first else { continue }
        let line = candidate.string
        lines.append(line)
        line.enumerateSubstrings(in: line.startIndex..<line.endIndex, options: .byWords) { word, range, _, _ in
            guard let word = word, let box = try? candidate.boundingBox(for: range) else { return }
            let r = box.boundingBox  // 0...1, origin at the bottom left
            words.append([
                "t": word,
                "x": Double(r.minX),
                "y": Double(1 - r.maxY),  // origin at the top left, like a web page
                "w": Double(r.width),
                "h": Double(r.height),
            ])
        }
    }
    results.append([
        "path": path,
        "text": lines.joined(separator: "\n"),
        "words": words,
        "width": cg.width,
        "height": cg.height,
    ])
}

if let data = try? JSONSerialization.data(withJSONObject: results) {
    FileHandle.standardOutput.write(data)
}
