import AppKit
import Foundation
import PDFKit
import Vision

struct OCRPage: Codable {
    let page_number: Int
    let text: String
    let confidence: Double
}

struct OCRPayload: Codable {
    let engine: String
    let page_count: Int
    let pages_processed: Int
    let pages: [OCRPage]
    let errors: [String]
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(2)
}

guard CommandLine.arguments.count >= 2 else {
    fail("Uso: swift ocr_pdf_macos_vision.swift arquivo.pdf [max_pages] [pt-BR,en-US] [1,3,8]")
}

let pdfURL = URL(fileURLWithPath: CommandLine.arguments[1])
let maxPages = CommandLine.arguments.count >= 3 ? Int(CommandLine.arguments[2]) ?? 0 : 0
let languages = CommandLine.arguments.count >= 4
    ? CommandLine.arguments[3].split(separator: ",").map(String.init).filter { !$0.isEmpty }
    : ["pt-BR", "en-US"]
let requestedPages = CommandLine.arguments.count >= 5
    ? CommandLine.arguments[4].split(separator: ",").compactMap { Int($0) }
    : []

guard let document = PDFDocument(url: pdfURL) else {
    fail("Não foi possível abrir o PDF: \(pdfURL.path)")
}

let pageCount = document.pageCount
let limit = maxPages > 0 ? min(pageCount, maxPages) : pageCount
let pageIndices: [Int]
if requestedPages.isEmpty {
    pageIndices = Array(0..<limit)
} else {
    pageIndices = Array(Set(requestedPages))
        .filter { $0 >= 1 && $0 <= limit }
        .sorted()
        .map { $0 - 1 }
}
var outputPages: [OCRPage] = []
var errors: [String] = []

for pageIndex in pageIndices {
    autoreleasepool {
        guard let page = document.page(at: pageIndex) else {
            errors.append("p.\(pageIndex + 1): página indisponível")
            outputPages.append(OCRPage(page_number: pageIndex + 1, text: "", confidence: 0.0))
            return
        }

        let bounds = page.bounds(for: .mediaBox)
        let longestSide = max(bounds.width, bounds.height)
        let scale = longestSide > 0 ? min(3.0, max(1.5, 2600.0 / longestSide)) : 2.0
        let targetSize = NSSize(width: max(bounds.width * scale, 1), height: max(bounds.height * scale, 1))
        let image = page.thumbnail(of: targetSize, for: .mediaBox)
        var proposedRect = NSRect(origin: .zero, size: image.size)
        guard let cgImage = image.cgImage(forProposedRect: &proposedRect, context: nil, hints: nil) else {
            errors.append("p.\(pageIndex + 1): renderização sem CGImage")
            outputPages.append(OCRPage(page_number: pageIndex + 1, text: "", confidence: 0.0))
            return
        }

        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = true
        request.recognitionLanguages = languages
        request.minimumTextHeight = 0.004

        do {
            let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
            try handler.perform([request])
            let observations = (request.results ?? []).sorted { lhs, rhs in
                let verticalGap = abs(lhs.boundingBox.midY - rhs.boundingBox.midY)
                if verticalGap > 0.012 {
                    return lhs.boundingBox.midY > rhs.boundingBox.midY
                }
                return lhs.boundingBox.minX < rhs.boundingBox.minX
            }
            let candidates = observations.compactMap { $0.topCandidates(1).first }
            let text = candidates.map(\.string).joined(separator: "\n")
            let confidence = candidates.isEmpty
                ? 0.0
                : candidates.map { Double($0.confidence) }.reduce(0, +) / Double(candidates.count)
            outputPages.append(OCRPage(page_number: pageIndex + 1, text: text, confidence: confidence))
        } catch {
            errors.append("p.\(pageIndex + 1): \(error.localizedDescription)")
            outputPages.append(OCRPage(page_number: pageIndex + 1, text: "", confidence: 0.0))
        }
    }
}

let payload = OCRPayload(
    engine: "macos_vision",
    page_count: pageCount,
    pages_processed: outputPages.count,
    pages: outputPages,
    errors: errors
)
let encoder = JSONEncoder()
encoder.outputFormatting = [.withoutEscapingSlashes]
do {
    let data = try encoder.encode(payload)
    FileHandle.standardOutput.write(data)
} catch {
    fail("Não foi possível serializar o resultado OCR: \(error.localizedDescription)")
}
