import Foundation
import Vision
import ImageIO

let arguments = CommandLine.arguments
if arguments.count != 3 { exit(2) }
let imageURL = URL(fileURLWithPath: arguments[1])
guard let source = CGImageSourceCreateWithURL(imageURL as CFURL, nil), let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else { exit(3) }
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["pt-BR", "en-US"]
request.usesLanguageCorrection = false
request.usesCPUOnly = true
try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
let rows: [[String: Any]] = (request.results ?? []).compactMap { item in
    guard let candidate = item.topCandidates(1).first else { return nil }
    return ["text": candidate.string, "confidence": candidate.confidence,
            "x": item.boundingBox.minX, "y": item.boundingBox.minY,
            "width": item.boundingBox.width, "height": item.boundingBox.height]
}
let payload: [String: Any] = ["engine": "Apple Vision", "recognition_languages": request.recognitionLanguages,
                           "lines": rows, "line_count": rows.count]
let output = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys, .prettyPrinted])
try output.write(to: URL(fileURLWithPath: arguments[2]), options: [.atomic])
