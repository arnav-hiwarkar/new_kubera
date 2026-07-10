import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { auditeaseAuditorApi } from '@/api/auditease-auditor';
import { Button } from '@/components/ui/button';

import { Textarea } from '@/components/ui/textarea';
import { MessageSquare, ArrowLeft, Send, CheckCircle2, Paperclip } from 'lucide-react';
import type { QueryResponse, QueryMessageResponse } from '@/types/auditease';

export function AuditorQueriesTab({ engagementId }: { engagementId: string }) {
  const queryClient = useQueryClient();
  const [activeQueryId, setActiveQueryId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [newMessage, setNewMessage] = useState('');

  const { data: queries = [], isLoading: queriesLoading } = useQuery({
    queryKey: ['auditor', 'engagements', engagementId, 'queries'],
    queryFn: () => auditeaseAuditorApi.getQueries(engagementId),
    enabled: !!engagementId,
  });

  const { data: activeQuery, isLoading: queryLoading } = useQuery({
    queryKey: ['auditor', 'engagements', engagementId, 'queries', activeQueryId],
    queryFn: () => auditeaseAuditorApi.getQuery(engagementId, activeQueryId!),
    enabled: !!activeQueryId,
  });

  const createQueryMutation = useMutation({
    mutationFn: (initial_message: string) => auditeaseAuditorApi.createQuery(engagementId, { initial_message, attached_document_id: null }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['auditor', 'engagements', engagementId, 'queries'] });
      setIsCreating(false);
      setNewMessage('');
      setActiveQueryId(data.id);
    },
  });

  const addMessageMutation = useMutation({
    mutationFn: (text: string) => auditeaseAuditorApi.addQueryMessage(engagementId, activeQueryId!, { text, attached_document_id: null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auditor', 'engagements', engagementId, 'queries', activeQueryId] });
      setNewMessage('');
    },
  });

  const closeQueryMutation = useMutation({
    mutationFn: () => auditeaseAuditorApi.closeQuery(engagementId, activeQueryId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auditor', 'engagements', engagementId, 'queries'] });
      queryClient.invalidateQueries({ queryKey: ['auditor', 'engagements', engagementId, 'queries', activeQueryId] });
    },
  });

  const handleCreateSubmit = () => {
    if (!newMessage.trim()) return;
    createQueryMutation.mutate(newMessage);
  };

  const handleReplySubmit = () => {
    if (!newMessage.trim()) return;
    addMessageMutation.mutate(newMessage);
  };

  if (queriesLoading) return <div className="text-sm text-muted-foreground p-6">Loading queries...</div>;

  if (activeQueryId || isCreating) {
    return (
      <div className="bg-card border border-border rounded-md flex flex-col h-[600px]">
        <div className="p-4 border-b border-border flex justify-between items-center bg-muted/20">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" onClick={() => { setActiveQueryId(null); setIsCreating(false); setNewMessage(''); }}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <h3 className="text-lg font-medium">
              {isCreating ? 'New Query Thread' : 'Query Thread'}
            </h3>
          </div>
          {activeQuery?.status === 'open' && (
            <Button variant="outline" size="sm" onClick={() => closeQueryMutation.mutate()} disabled={closeQueryMutation.isPending}>
              <CheckCircle2 className="h-4 w-4 mr-2" />
              Close Thread
            </Button>
          )}
          {activeQuery?.status === 'closed' && (
            <span className="text-sm bg-muted text-muted-foreground px-3 py-1 rounded-full">Closed</span>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {isCreating ? (
            <div className="text-sm text-muted-foreground">Start a new discussion with the client.</div>
          ) : queryLoading ? (
            <div className="text-sm text-muted-foreground">Loading thread...</div>
          ) : (
            activeQuery?.messages.map((msg: QueryMessageResponse) => (
              <div key={msg.id} className={`flex flex-col max-w-[80%] ${msg.sender_type === 'auditor' ? 'ml-auto items-end' : 'mr-auto items-start'}`}>
                <span className="text-xs text-muted-foreground mb-1 px-1">
                  {msg.sender_type === 'auditor' ? 'You' : 'Client'} • {new Date(msg.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                </span>
                <div className={`p-3 rounded-lg text-sm whitespace-pre-wrap ${
                  msg.sender_type === 'auditor' 
                    ? 'bg-primary text-primary-foreground rounded-tr-none' 
                    : 'bg-muted text-foreground rounded-tl-none border border-border'
                }`}>
                  {msg.text}
                </div>
              </div>
            ))
          )}
        </div>

        {(!activeQuery || activeQuery.status === 'open' || isCreating) && (
          <div className="p-4 border-t border-border bg-muted/10 flex gap-2 items-end">
            <div className="flex-1">
              <Textarea 
                value={newMessage}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setNewMessage(e.target.value)}
                placeholder={isCreating ? "Type your initial question..." : "Type your reply..."}
                className="min-h-[80px] resize-none"
              />
            </div>
            {/* For simplicity, omitting file attachment logic here, but placeholder icon is shown */}
            <Button variant="outline" size="icon" className="h-10 w-10 shrink-0" title="Attach file (not implemented)">
              <Paperclip className="h-4 w-4 text-muted-foreground" />
            </Button>
            <Button 
              onClick={isCreating ? handleCreateSubmit : handleReplySubmit}
              disabled={!newMessage.trim() || createQueryMutation.isPending || addMessageMutation.isPending}
              className="h-10"
            >
              <Send className="h-4 w-4 mr-2" />
              {isCreating ? 'Start' : 'Send'}
            </Button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="bg-card border border-border rounded-md p-6 h-full flex flex-col">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h3 className="text-lg font-medium text-foreground">Queries</h3>
          <p className="text-sm text-muted-foreground">Discuss items and ask questions to the client.</p>
        </div>
        <Button onClick={() => setIsCreating(true)} size="sm">
          <MessageSquare className="h-4 w-4 mr-2" />
          New Query
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto space-y-3">
        {queries.length === 0 ? (
          <div className="text-center p-8 border border-dashed border-border rounded-md">
            <MessageSquare className="h-8 w-8 mx-auto text-muted-foreground mb-3 opacity-50" />
            <p className="text-sm text-muted-foreground">No queries yet.</p>
          </div>
        ) : (
          queries.map((query: QueryResponse) => {
            const lastMsg = query.messages?.[query.messages.length - 1];
            return (
              <div 
                key={query.id} 
                className="p-4 border border-border rounded-md bg-muted/10 hover:bg-muted/30 cursor-pointer transition-colors flex items-center justify-between"
                onClick={() => setActiveQueryId(query.id)}
              >
                <div className="flex-1 truncate pr-4">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${query.status === 'open' ? 'bg-blue-500/10 text-blue-500' : 'bg-muted text-muted-foreground'}`}>
                      {query.status.toUpperCase()}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      Opened {new Date(query.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <p className="text-sm text-foreground truncate">
                    {lastMsg ? lastMsg.text : 'No messages'}
                  </p>
                </div>
                <Button variant="ghost" size="sm">View</Button>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
