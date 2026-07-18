import { Module } from '@nestjs/common';
import { PublishingAgentService } from './publishing-agent.service';
import { AiProviderModule } from '../ai-provider/ai-provider.module';
import { PostsModule } from '../database/prisma/posts/posts.module';
import { IntegrationsModule } from '../database/prisma/integrations/integrations.module';

@Module({
  imports: [AiProviderModule, PostsModule, IntegrationsModule],
  providers: [PublishingAgentService],
  exports: [PublishingAgentService]
})
export class PublishingAgentModule {}
