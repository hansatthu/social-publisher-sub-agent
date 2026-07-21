import { NextRequest, NextResponse } from 'next/server';
import { createReadStream, existsSync, statSync } from 'fs';
import { join } from 'path';
// @ts-ignore
import mime from 'mime';
async function* nodeStreamToIterator(stream: any) {
  for await (const chunk of stream) {
    yield chunk;
  }
}
function iteratorToStream(iterator: any) {
  return new ReadableStream({
    async pull(controller) {
      const { value, done } = await iterator.next();
      if (done) {
        controller.close();
      } else {
        controller.enqueue(new Uint8Array(value));
      }
    },
  });
}
export const GET = async (
  request: NextRequest,
  context: {
    params: Promise<{
      path?: string[];
    }>;
  }
) => {
  const { path } = await context.params;
  const uploadDirectory = process.env.UPLOAD_DIRECTORY;

  if (!uploadDirectory) {
    return NextResponse.json(
      { error: 'UPLOAD_DIRECTORY is not configured on the server.' },
      { status: 500 }
    );
  }

  if (!path?.length) {
    return NextResponse.json(
      { error: 'Missing upload file path.' },
      { status: 400 }
    );
  }

  const normalizedUploadDirectory = join(uploadDirectory);
  const filePath = join(normalizedUploadDirectory, ...path);

  if (!filePath.startsWith(normalizedUploadDirectory)) {
    return NextResponse.json(
      { error: 'Invalid upload file path.' },
      { status: 400 }
    );
  }

  if (!existsSync(filePath)) {
    return NextResponse.json({ error: 'Upload file not found.' }, { status: 404 });
  }

  const response = createReadStream(filePath);
  const fileStats = statSync(filePath);
  const contentType = mime.getType(filePath) || 'application/octet-stream';
  const iterator = nodeStreamToIterator(response);
  const webStream = iteratorToStream(iterator);
  return new Response(webStream, {
    headers: {
      'Content-Type': contentType,
      // Set the appropriate content-type header
      'Content-Length': fileStats.size.toString(),
      // Set the content-length header
      'Last-Modified': fileStats.mtime.toUTCString(),
      // Set the last-modified header
      'Cache-Control': 'public, max-age=31536000, immutable',
    },
  });
};
