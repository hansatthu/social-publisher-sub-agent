import { Injectable, BadRequestException, Inject } from '@nestjs/common';
import { AIProvider } from '../ai-provider/ai.provider.interface';
import { PostsService } from '../database/prisma/posts/posts.service';
import { CreatePostDto } from '../dtos/posts/create.post.dto';
import { IntegrationService } from '../database/prisma/integrations/integration.service';
import dayjs from 'dayjs';

@Injectable()
export class PublishingAgentService {
  constructor(
    @Inject('AIProvider') private readonly aiProvider: AIProvider,
    private readonly postsService: PostsService,
    private readonly integrationService: IntegrationService
  ) {}

  async generateContent(mode: 1 | 2 | 3, prompt?: string, content?: string, variations: number = 1) {
    if (mode === 1) {
      if (!prompt) throw new BadRequestException('Prompt is required for mode 1');
      const text = await this.aiProvider.generateText(prompt);
      return text[0];
    }
    
    if (mode === 2) {
      if (!content) throw new BadRequestException('Content is required for mode 2');
      return content;
    }
    
    if (mode === 3) {
      if (!prompt) throw new BadRequestException('Prompt is required for mode 3');
      const texts = await this.aiProvider.generateText(prompt, { variations });
      return texts;
    }

    throw new BadRequestException('Invalid content mode');
  }

  async generateImage(mode: 1 | 2 | 3, prompt?: string, imageUrl?: string) {
    if (mode === 1) {
      if (!prompt) throw new BadRequestException('Prompt is required for mode 1');
      const images = await this.aiProvider.generateImage(prompt);
      return images[0];
    }

    if (mode === 2) {
      if (!imageUrl) throw new BadRequestException('Image URL is required for mode 2');
      return imageUrl;
    }

    if (mode === 3) {
      // Product image library logic
      // In a real implementation this would fetch from a database or asset manager
      if (!prompt) throw new BadRequestException('Product search term (prompt) is required for mode 3');
      return `https://example.com/product-library/${prompt.replace(/ /g, '-')}.png`;
    }

    throw new BadRequestException('Invalid image mode');
  }

  async publish(orgId: string, destinations: string[], content: string, images: string[] = [], date?: string, isBulk: boolean = false) {
    const delaySeconds = parseInt(process.env.PUBLISH_DELAY_SECONDS || '300', 10);
    const startDate = date ? dayjs(date) : dayjs();

    // Map the external request to the CreatePostDto used by the platform
    for (let i = 0; i < destinations.length; i++) {
      const destId = destinations[i];
      // For bulk, add delay
      const postDate = isBulk ? startDate.add(i * delaySeconds, 'second') : startDate;
      
      const integration = await this.integrationService.getIntegrationById(orgId, destId);
      if (!integration) {
         throw new BadRequestException(`Integration ${destId} not found`);
      }

      const createDto: CreatePostDto = {
        type: postDate.diff(dayjs()) > 60000 ? 'schedule' : 'now',
        shortLink: false,
        date: postDate.toISOString(),
        tags: [],
        posts: [
          {
            integration: { id: destId },
            group: '',
            value: [
              {
                id: '',
                content: content,
                image: images.map(img => ({ path: img, id: '' })),
                delay: 0
              }
            ],
            settings: {
              __type: integration.providerIdentifier
            } as any
          }
        ]
      };

      const mappedBody = await this.postsService.mapTypeToPost(createDto, orgId);
      await this.postsService.createPost(orgId, mappedBody, 'WEB');
    }

    return { status: 'Jobs submitted', destinationsCount: destinations.length };
  }

  async getJobs(orgId: string) {
    return this.postsService.getPostsList(orgId, { page: 1 });
  }

  async getJob(orgId: string, id: string) {
    return this.postsService.getPost(orgId, id);
  }
}
