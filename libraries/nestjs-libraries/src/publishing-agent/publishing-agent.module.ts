import { Module } from '@nestjs/common';
import { PublishingAgentService } from './publishing-agent.service';
import { AiProviderModule } from '../ai-provider/ai-provider.module';
import { DatabaseModule } from '../database/prisma/database.module';

@Module({
  imports: [AiProviderModule, DatabaseModule],
  providers: [PublishingAgentService],
  exports: [PublishingAgentService]
})
export class PublishingAgentModule {}
