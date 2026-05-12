# efficientnet_detector_v2.py
import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision.models import efficientnet_b0, EfficientNet_B0_Weights
from torch_dct import dct_2d

# ----------------------------------------------------------------------
#        Attention & 基础模块
# ----------------------------------------------------------------------
class SEBlock1D(nn.Module):
  def __init__(self, channels, r=4):
      super().__init__()
      self.fc = nn.Sequential(
        nn.Linear(channels, channels//r, bias=False),
        nn.ReLU(inplace=True),
        nn.Linear(channels//r, channels, bias=False),
        nn.Sigmoid()
      )
  def forward(self, x):   # x: (B, C)
      w = self.fc(x)      # (B, C)
      return x * w


class DCTLayer(nn.Module):
    def __init__(self):
        super().__init__()

    def forward(self, x):
        B, C, H, W = x.shape
        x_flat = x.view(B*C, H, W)
        X = dct_2d(x_flat).view(B, C, H, W)
        mean = X.mean(dim=(-2, -1), keepdim=True)
        std  = X.std(dim=(-2, -1), keepdim=True).clamp(min=1e-6)
        X_norm = (X - mean) / std
        return X_norm
    '''
        # Min-Max 归一化
        min_val = X_norm.amin(dim=(-2, -1), keepdim=True)
        max_val = X_norm.amax(dim=(-2, -1), keepdim=True)
        X_minmax = (X_norm - min_val) / (max_val - min_val + 1e-6)
        
        return X_minmax
    '''


class GradLayer(nn.Module):
    def __init__(self):
        super().__init__()
        gx = torch.tensor([[1,0,-1],[2,0,-2],[1,0,-1]], dtype=torch.float32)
        gy = gx.t()
        # 重复三份，变成 (3,1,3,3)，groups=3 分组卷积
        self.register_buffer('gx', gx.view(1,1,3,3).repeat(3,1,1,1))
        self.register_buffer('gy', gy.view(1,1,3,3).repeat(3,1,1,1))

    def forward(self, x):
        # x: (B,3,H,W)
        g_x = F.conv2d(x, self.gx, padding=1, groups=3)  # -> (B,3,H,W)
        g_y = F.conv2d(x, self.gy, padding=1, groups=3)
        P = torch.sqrt(g_x**2 + g_y**2 + 1e-6)                  # (B,3,H,W)
        # 归一化到 [0,1]，在 H/W 维度上做 min-max
        
        mean = P.mean(dim=(-2,-1), keepdim=True)
        mins = P.amin(dim=(-2,-1), keepdim=True)
        maxs = P.amax(dim=(-2,-1), keepdim=True)
        return (P - mins) / (maxs - mins + 1e-6)
        '''
        std  = P.std(dim=(-2,-1), keepdim=True).clamp(min=1e-6)
        P_norm = (P - mean) / std
        return P_norm
        '''

# ----------------------------------------------------------------------
#       跨分支 Attention
# ----------------------------------------------------------------------
class BranchCrossAttention(nn.Module):
    """
    Attention + FeedForward + 双残差 (Transformer Encoder 风格)：
      1) Multi-Head Attention
      2) Feed-Forward Network
      3) 可学习门控 g 控制 FFN 残差强度
    输入输出形状均为 (B, N, C)
    """
    def __init__(self, dim, heads=None, ffn_expansion=4, dropout=0.1):
        super().__init__()
        # 自动找一个能整除 dim 的 heads（≈dim/4）
        if heads is None:
            heads = max(1, dim // 4)
            while dim % heads != 0 and heads > 1:
                heads -= 1
        self.mha = nn.MultiheadAttention(dim, heads, dropout=dropout,
                                         batch_first=True)
        self.dropout = nn.Dropout(dropout)
        self.ln1 = nn.LayerNorm(dim)

        # Feed-Forward
        self.ffn = nn.Sequential(
            nn.Linear(dim, dim * ffn_expansion),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(dim * ffn_expansion, dim),
            nn.Dropout(dropout)
        )
        self.gate = nn.Parameter(torch.ones(1))   # 可学习放缩系数
        self.ln2 = nn.LayerNorm(dim)

    def forward(self, q, kv):
        # --- Self / Cross-Attention block ---
        attn_out, _ = self.mha(q, kv, kv)         # (B,N,C)
        x = self.ln1(q + self.dropout(attn_out))  # 残差 1

        # --- Position-wise Feed-Forward block ---
        ffn_out = self.ffn(x)
        x = self.ln2(x + self.gate * ffn_out)     # 残差 2 + 门控
        return x


# ----------------------------------------------------------------------
# ✅ 基础网络分支
# ----------------------------------------------------------------------
class Effb0Branch(nn.Module):
    """EfficientNet-b0 去头特征提取 + 降维到 16D"""
    def __init__(self, out_dim=16, pretrained=True):
        super().__init__()
        # 加载预训练模型，去掉分类头
        backbone = efficientnet_b0(weights=EfficientNet_B0_Weights.IMAGENET1K_V1 if pretrained else None)
        self.features = backbone.features  # 特征提取部分
        self.pool = nn.AdaptiveAvgPool2d(1)
        # EfficientNet_b0 最后 feature map 通道数为 1280
        self.dim_reduce = nn.Sequential(
            nn.Dropout(0.5),
            nn.Linear(1280, out_dim),
            nn.LeakyReLU(0.1,inplace=True),
            nn.Dropout(0.5),
        )

    def forward(self, x):
        x = self.features(x)           # (B, 1280, h, w)
        x = self.pool(x).flatten(1)    # (B, 1280)
        x = self.dim_reduce(x)         # (B, out_dim)
        return x


class BaseCNN(nn.Module):
    def __init__(self, in_channels = 3,first_channels=8,activation='relu'):
        super().__init__()
        if activation == 'leakyrelu':
            act = nn.LeakyReLU(0.1, inplace=True)
        else:
            act = nn.ReLU(inplace=True)
        
        self.conv1 = nn.Sequential(
            nn.Conv2d(in_channels, first_channels, 3, padding=1, bias=False),  
            nn.BatchNorm2d(first_channels),   
            act,
            #CBAMBlock(first_channels), 
            nn.MaxPool2d(2)                                  
        )

        self.conv2 = nn.Sequential(
            nn.Conv2d(first_channels, first_channels, 5, padding=2, bias=False),
            nn.BatchNorm2d(first_channels),   
            act,
            #CBAMBlock(first_channels), 
            nn.MaxPool2d(2)                                  
        )

        self.conv3 = nn.Sequential(
            nn.Conv2d(first_channels, first_channels*2, 5, padding=2, bias=False),
            nn.BatchNorm2d(first_channels*2),   
            act,
            #CBAMBlock(first_channels*2), 
            nn.MaxPool2d(2)                                   
        )

        self.conv4 = nn.Sequential(
            nn.Conv2d(first_channels*2, first_channels*2, 5, padding=2, bias=False),
            nn.BatchNorm2d(first_channels*2),   
            act,
            #CBAMBlock(first_channels*2), 
            nn.MaxPool2d(4)                                   
        )

        self.dropout = nn.Dropout(0.5)
        self.fc      = nn.Linear(first_channels*2 * 8 * 8, 16)
        self.act     = nn.LeakyReLU(0.1,inplace=True)

    def forward(self, x):
        x = self.conv1(x)
        x = self.conv2(x)
        x = self.conv3(x)
        x = self.conv4(x)               
        x = x.flatten(1)                
        x = self.dropout(x)
        x = self.fc(x)
        x = self.act(x)
        return self.dropout(x)          


# ----------------------------------------------------------------------
# ✅ Detector 主体
# ----------------------------------------------------------------------
class EfficientNetDetector(nn.Module):
    def __init__(self, feat_dim=16, pretrained=True, attn_heads=None):
        super().__init__()
        # 归一化常数
        self.register_buffer('mean', torch.tensor([0.485, 0.456, 0.406])
                             .view(1, 3, 1, 1))
        self.register_buffer('std', torch.tensor([0.229, 0.224, 0.225])
                             .view(1, 3, 1, 1))

        # 三条分支
        self.spatial_branch = Effb0Branch(out_dim=feat_dim,
                                          pretrained=pretrained)

        self.grad_branch = nn.Sequential(
            GradLayer(),
            nn.Conv2d(3, 16, 3, padding=1, bias=False),
            nn.BatchNorm2d(16), nn.ReLU(inplace=True),
            #CBAMBlock(16),
            BaseCNN(in_channels=16, first_channels=8)
        )

        self.freq_branch = nn.Sequential(
            DCTLayer(),
            nn.Conv2d(3, 16, 3, padding=1, bias=False),
            nn.BatchNorm2d(16), nn.LeakyReLU(0.1, inplace=True),
            #CBAMBlock(16),
            BaseCNN(in_channels=16, first_channels=8, activation='leakyrelu')
        )

        # 改进版跨分支 Attention
        self.rgb2subs_attn = BranchCrossAttention(feat_dim, heads=attn_heads)
        self.subs_mutual   = BranchCrossAttention(feat_dim, heads=attn_heads)

        # 融合 + 分类
        self.fusion = nn.Sequential(
            nn.Linear(3 * feat_dim, 2 * feat_dim),
            nn.BatchNorm1d(2 * feat_dim),
            nn.LeakyReLU(0.1, inplace=True),
            nn.Dropout(0.3),
            SEBlock1D(2 * feat_dim),
            nn.Linear(2 * feat_dim, feat_dim),
            nn.LeakyReLU(0.1, inplace=True)
        )
        self.classifier = nn.Linear(feat_dim, 1)

    def forward(self, x):
        # 主分支
        spa = self.spatial_branch(x)  # (B,C)

        # 子分支输入反归一化到 [0,1]
        xn = (x * self.std + self.mean).clamp(0, 1)
        grd = self.grad_branch(xn)
        fre = self.freq_branch(xn)

        # ---------- 跨分支注意 ----------
        spa_new = self.rgb2subs_attn(spa.unsqueeze(1),
                                     torch.stack([grd, fre], dim=1))  # (B,1,C)
        subs_new = self.subs_mutual(torch.stack([grd, fre], dim=1),
                                    torch.stack([grd, fre], dim=1))    # (B,2,C)
        grd_new, fre_new = subs_new[:, 0], subs_new[:, 1]

        # ---------- 融合 ----------
        fused = self.fusion(
            torch.cat([spa_new.squeeze(1), grd_new, fre_new], dim=1)
        )
        return self.classifier(fused).squeeze(1)