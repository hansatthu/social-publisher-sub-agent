export interface AIProvider {
  /**
   * Generate text content using the AI provider.
   * @param prompt The prompt to send to the AI
   * @param options Additional generation options (e.g. variations count, model, system instruction)
   * @returns An array of generated strings. If variations > 1, returns multiple strings.
   */
  generateText(prompt: string, options?: { variations?: number; systemInstruction?: string }): Promise<string[]>;

  /**
   * Generate an image using the AI provider.
   * @param prompt The prompt to send to the AI
   * @param options Additional generation options
   * @returns An array of generated image URLs or base64 strings.
   */
  generateImage(prompt: string, options?: { variations?: number }): Promise<string[]>;
}
