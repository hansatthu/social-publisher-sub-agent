import { Body, Controller, Get, Param, Post } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';
import { PublishingAgentService } from '@gitroom/nestjs-libraries/publishing-agent/publishing-agent.service';
import { GetOrgFromRequest } from '@gitroom/nestjs-libraries/user/org.from.request';
import { Organization } from '@prisma/client';

@ApiTags('Agent')
@Controller('/agent')
export class PublishingAgentController {
  constructor(private readonly agentService: PublishingAgentService) {}

  @Post('/generate-content')
  async generateContent(
    @Body() body: { mode: 1 | 2 | 3; prompt?: string; content?: string; variations?: number }
  ) {
    const result = await this.agentService.generateContent(
      body.mode,
      body.prompt,
      body.content,
      body.variations
    );
    return { data: result };
  }

  @Post('/generate-image')
  async generateImage(
    @Body() body: { mode: 1 | 2 | 3; prompt?: string; imageUrl?: string }
  ) {
    const result = await this.agentService.generateImage(
      body.mode,
      body.prompt,
      body.imageUrl
    );
    return { data: result };
  }

  @Post('/publish')
  async publish(
    @GetOrgFromRequest() org: Organization,
    @Body() body: { destinations: string[]; content: string; images?: string[] }
  ) {
    return this.agentService.publish(
      org.id,
      body.destinations,
      body.content,
      body.images || [],
      undefined,
      false
    );
  }

  @Post('/schedule')
  async schedule(
    @GetOrgFromRequest() org: Organization,
    @Body() body: { destinations: string[]; content: string; images?: string[]; date: string }
  ) {
    return this.agentService.publish(
      org.id,
      body.destinations,
      body.content,
      body.images || [],
      body.date,
      false
    );
  }

  @Post('/bulk-publish')
  async bulkPublish(
    @GetOrgFromRequest() org: Organization,
    @Body() body: { destinations: string[]; content: string; images?: string[]; date?: string }
  ) {
    return this.agentService.publish(
      org.id,
      body.destinations,
      body.content,
      body.images || [],
      body.date,
      true
    );
  }

  @Get('/jobs')
  async getJobs(@GetOrgFromRequest() org: Organization) {
    return this.agentService.getJobs(org.id);
  }

  @Get('/jobs/:id')
  async getJob(
    @GetOrgFromRequest() org: Organization,
    @Param('id') id: string
  ) {
    return this.agentService.getJob(org.id, id);
  }
}
