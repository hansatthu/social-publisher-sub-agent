import { Injectable, Logger } from '@nestjs/common';
import { AIProvider } from './ai.provider.interface';
import OpenAI from 'openai';

@Injectable()
export class DeepSeekProvider implements AIProvider {
  private openai: OpenAI;
  private readonly logger = new Logger(DeepSeekProvider.name);

  constructor() {
    this.openai = new OpenAI({
      apiKey: process.env.DEEPSEEK_API_KEY || '',
      baseURL: 'https://api.deepseek.com',
    });
  }

  async generateText(
    prompt: string,
    options?: { variations?: number; systemInstruction?: string }
  ): Promise<string[]> {
    const variations = options?.variations || 1;
    const messages: any[] = [];
    
    if (options?.systemInstruction) {
      messages.push({ role: 'system', content: options.systemInstruction });
    }
    messages.push({ role: 'user', content: prompt });

    try {
      const response = await this.openai.chat.completions.create({
        model: 'deepseek-chat',
        messages,
        n: variations,
      });

      return response.choices.map((choice) => choice.message.content || '');
    } catch (error) {
      this.logger.error(`Error generating text with DeepSeek: ${error.message}`);
      throw error;
    }
  }

  async generateImage(
    prompt: string,
    options?: { variations?: number }
  ): Promise<string[]> {
    // DeepSeek currently does not have an image generation endpoint in its public API.
    // For now, this is a placeholder or you would route this to a different model/provider
    // if DeepSeek adds image generation.
    this.logger.warn('Image generation is not supported by DeepSeek natively yet.');
    throw new Error('Method not implemented.');
  }
}
