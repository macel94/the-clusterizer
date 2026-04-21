export interface AnalysisCreate {
  jira_url: string;
  username?: string;
  pat: string;
  jql_filter: string;
  num_clusters: number;
}

export interface RepresentativeTicket {
  key: string;
  summary: string;
}

export interface ClusterInfo {
  id: string;
  cluster_number: number;
  label: string;
  ticket_count: number;
  keywords?: string[];
  representative_tickets?: RepresentativeTicket[];
  percentage?: number;
}

export type AnalysisStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface Analysis {
  id: string;
  jira_url: string;
  username?: string;
  jql_filter: string;
  num_clusters: number;
  status: AnalysisStatus;
  error_message?: string;
  total_tickets: number;
  created_at: string;
  completed_at?: string;
  clusters?: ClusterInfo[];
}
