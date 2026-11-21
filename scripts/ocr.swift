// Reads the text in screenshots and photos using Apple's on-device Vision
// framework (the same text reader the Photos app uses). Nothing goes online.
// It writes nothing to disk: results are printed for Codicilix to read.
//
// Built once by scripts/make-mac-app.sh:
//   swiftc -O scripts/ocr.swift -o bin/second-brain-ocr
// Usage:
//   bin/second-brain-ocr image1.png image2.jpg ...

import AppKit
import Foundation
import Vision

var results: [[String: String]] = []

for path in CommandLine.arguments.dropFirst() {
    let url = URL(fileURLWithPath: path)
    guard let image = NSImage(contentsOf: url),
          let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
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
    let observations = (request.results as? [VNRecognizedTextObservation]) ?? []
    // Top of the image first, then left to right.
    let sorted = observations.sorted {
        let dy = $0.boundingBox.midY - $1.boundingBox.midY
        if abs(dy) > 0.02 { return dy > 0 }
        return $0.boundingBox.minX < $1.boundingBox.minX
    }
    let lines = sorted.compactMap { $0.topCandidates(1).first?.string }
    results.append(["path": path, "text": lines.joined(separator: "\n")])
}

if let data = try? JSONSerialization.data(withJSONObject: results) {
    FileHandle.standardOutput.write(data)
}
