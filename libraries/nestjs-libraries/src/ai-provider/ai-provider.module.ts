import { Module } from '@nestjs/common';
import { DeepSeekProvider } from './deepseek.provider';

@Module({
  providers: [
    {
      provide: 'AIProvider',
      useFactory: () => {
        // Here we could switch based on process.env.DEFAULT_AI_PROVIDER
        // For now, we return DeepSeekProvider as requested
        return new DeepSeekProvider();
      },
    },
  ],
  exports: ['AIProvider'],
})
export class AiProviderModule {}
