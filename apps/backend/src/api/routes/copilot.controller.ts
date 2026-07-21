import OpenAI from 'openai';
import {
  Logger,
  Controller,
  Get,
  Post,
  Req,
  Res,
  Query,
  Param,
} from '@nestjs/common';
import {
  CopilotRuntime,
  OpenAIAdapter,
  copilotRuntimeNodeHttpEndpoint,
  copilotRuntimeNextJSAppRouterEndpoint,
} from '@copilotkit/runtime';
import { GetOrgFromRequest } from '@gitroom/nestjs-libraries/user/org.from.request';
import { Organization } from '@prisma/client';
import { SubscriptionService } from '@gitroom/nestjs-libraries/database/prisma/subscriptions/subscription.service';
import { MastraAgent } from '@ag-ui/mastra';
import { MastraService } from '@gitroom/nestjs-libraries/chat/mastra.service';
import { Request, Response } from 'express';
import { RequestContext } from '@mastra/core/di';
import { CheckPolicies } from '@gitroom/backend/services/auth/permissions/permissions.ability';
import { AuthorizationActions, Sections } from '@gitroom/backend/services/auth/permissions/permission.exception.class';

export type ChannelsContext = {
  integrations: string;
  organization: string;
  ui: string;
};

/**
 * Creates a patched OpenAI instance that remaps the unsupported `developer`
 * role to `system` before forwarding requests to DeepSeek's API.
 *
 * CopilotKit's OpenAIAdapter sends `role: "developer"` as the system prompt
 * (an OpenAI o1/o3-only feature). DeepSeek only accepts:
 * system | user | assistant | tool | latest_reminder
 */
function createDeepSeekClient(): OpenAI {
  const client = new OpenAI({
    apiKey: process.env.DEEPSEEK_API_KEY,
    baseURL: 'https://api.deepseek.com/v1',
  });

  // Patch chat.completions.create to remap 'developer' role -> 'system'
  const originalCreate = client.chat.completions.create.bind(client.chat.completions);
  (client.chat.completions as any).create = (params: any, options?: any) => {
    if (params?.messages && Array.isArray(params.messages)) {
      params = {
        ...params,
        messages: params.messages.map((msg: any) =>
          msg.role === 'developer' ? { ...msg, role: 'system' } : msg
        ),
      };
    }
    return originalCreate(params, options);
  };

  const originalStream = client.chat.completions.stream.bind(client.chat.completions);
  (client.chat.completions as any).stream = (params: any, options?: any) => {
    console.log("PATCHED STREAM CALLED! messages count:", params?.messages?.length);
    if (params?.messages && Array.isArray(params.messages)) {
      params = {
        ...params,
        messages: params.messages.map((msg: any) => {
          if (msg.role === 'developer') {
            console.log("REPLACING DEVELOPER ROLE WITH SYSTEM");
            return { ...msg, role: 'system' };
          }
          return msg;
        }),
      };
    }
    return originalStream(params, options);
  };

  // CopilotKit uses client.beta.chat which is removed in openai v6
  (client as any).beta = {
    chat: client.chat,
  };

  return client;
}

@Controller('/copilot')
export class CopilotController {
  constructor(
    private _subscriptionService: SubscriptionService,
    private _mastraService: MastraService
  ) {}
  @Post('/chat')
  chatAgent(@Req() req: Request, @Res() res: Response) {
    if (
      !process.env.OPENAI_API_KEY && !process.env.DEEPSEEK_API_KEY
    ) {
      Logger.warn('AI API key not set, chat functionality will not work');
      return;
    }

    const isDeepseek = !!process.env.DEEPSEEK_API_KEY;
    const openaiInstance = isDeepseek ? createDeepSeekClient() : undefined;

    const copilotRuntimeHandler = copilotRuntimeNodeHttpEndpoint({
      endpoint: '/copilot/chat',
      runtime: new CopilotRuntime(),
      serviceAdapter: new OpenAIAdapter({
        openai: openaiInstance as any,
        model: isDeepseek ? 'deepseek-chat' : 'gpt-4o',
      }),
    });

    return copilotRuntimeHandler(req, res);
  }

  @Post('/agent')
  @CheckPolicies([AuthorizationActions.Create, Sections.AI])
  async agent(
    @Req() req: Request,
    @Res() res: Response,
    @GetOrgFromRequest() organization: Organization
  ) {
    if (
      !process.env.OPENAI_API_KEY && !process.env.DEEPSEEK_API_KEY
    ) {
      Logger.warn('AI API key not set, chat functionality will not work');
      return;
    }
    const mastra = await this._mastraService.mastra();
    const requestContext = new RequestContext<ChannelsContext>();
    requestContext.set(
      'integrations',
      req?.body?.variables?.properties?.integrations || []
    );

    requestContext.set('organization', JSON.stringify(organization));
    requestContext.set('ui', 'true');

    const agents = MastraAgent.getLocalAgents({
      resourceId: organization.id,
      mastra,
      requestContext: requestContext as any,
    });

    const runtime = new CopilotRuntime({
      agents,
    });

    const isDeepseek = !!process.env.DEEPSEEK_API_KEY;
    const openaiInstance = isDeepseek ? createDeepSeekClient() : undefined;

    const copilotRuntimeHandler = copilotRuntimeNextJSAppRouterEndpoint({
      endpoint: '/copilot/agent',
      runtime,
      // properties: req.body.variables.properties,
      serviceAdapter: new OpenAIAdapter({
        openai: openaiInstance as any,
        model: isDeepseek ? 'deepseek-chat' : 'gpt-4o',
        keepSystemRole: isDeepseek,
      }),
    });

    return copilotRuntimeHandler.handleRequest(req, res);
  }

  @Get('/credits')
  calculateCredits(
    @GetOrgFromRequest() organization: Organization,
    @Query('type') type: 'ai_images' | 'ai_videos'
  ) {
    return this._subscriptionService.checkCredits(
      organization,
      type || 'ai_images'
    );
  }

  @Get('/:thread/list')
  @CheckPolicies([AuthorizationActions.Create, Sections.AI])
  async getMessagesList(
    @GetOrgFromRequest() organization: Organization,
    @Param('thread') threadId: string
  ): Promise<any> {
    const mastra = await this._mastraService.mastra();
    const memory = await mastra.getAgent('postiz').getMemory();
    try {
      return await memory.recall({
        resourceId: organization.id,
        threadId,
      });
    } catch (err) {
      return { messages: [] };
    }
  }

  @Get('/list')
  @CheckPolicies([AuthorizationActions.Create, Sections.AI])
  async getList(@GetOrgFromRequest() organization: Organization) {
    const mastra = await this._mastraService.mastra();
    const memory = await mastra.getAgent('postiz').getMemory();
    const list = await memory.listThreads({
      filter: { resourceId: organization.id },
      perPage: 100000,
      page: 0,
      orderBy: { field: 'createdAt', direction: 'DESC' },
    });

    return {
      threads: list.threads.map((p) => ({
        id: p.id,
        title: p.title,
      })),
    };
  }
}
